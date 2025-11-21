import importlib
import os
import sys
import subprocess
from typing import Dict, List, Optional, Tuple

# Dependency check
REQUIRED_MODULES = ["pandas", "requests", "tqdm", "colorama"]


def ensure_dependencies() -> None:
    missing = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if not missing:
        return

    print("The following dependencies are missing:", ", ".join(missing))
    choice = input("Do you want to install them now with pip? [y/N]: ").strip().lower()
    if choice != "y":
        print("Cannot continue without required dependencies.")
        sys.exit(1)

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
    except subprocess.CalledProcessError:
        print("Failed to install dependencies automatically. Please install them manually and rerun the script.")
        sys.exit(1)


def clear_console() -> None:
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        pass


class QuotaExceeded(Exception):
    pass


class TranslationService:
    name: str = ""
    supports_context: bool = False

    def available_languages(self, role: str) -> List[Dict[str, str]]:
        raise NotImplementedError

    def translate(
        self,
        text: str,
        source_lang: Optional[str],
        target_lang: str,
        context: Optional[str] = None,
        purpose: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


class DeepLService(TranslationService):
    def __init__(self, auth_key: str):
        import requests

        self.auth_key = auth_key.strip()
        self.requests = requests
        self.supports_context = True
        self.base_url = "https://api-free.deepl.com/v2" if self.auth_key.endswith(":fx") else "https://api.deepl.com/v2"

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        return self.requests.request(method, url, timeout=15, **kwargs)

    def check_usage(self) -> Dict[str, int]:
        resp = self._request("GET", "/usage", params={"auth_key": self.auth_key})
        if resp.status_code == 403:
            raise ValueError("Authentication failed. Please check your DeepL API key.")
        resp.raise_for_status()
        return resp.json()

    def available_languages(self, role: str) -> List[Dict[str, str]]:
        resp = self._request("GET", "/languages", params={"auth_key": self.auth_key, "type": role})
        resp.raise_for_status()
        data = resp.json()
        languages = [{"code": item["language"], "name": item.get("name", item["language"])} for item in data]
        languages.sort(key=lambda x: x["name"].lower())
        return languages

    def translate(self, text: str, source_lang: Optional[str], target_lang: str, context: Optional[str] = None, purpose: Optional[str] = None) -> str:
        payload = {
            "auth_key": self.auth_key,
            "text": text,
            "target_lang": target_lang,
        }
        if source_lang:
            payload["source_lang"] = source_lang
        # Combine context and purpose into a single context string if provided
        context_value = None
        if context:
            context_value = context
        if purpose:
            context_value = (context_value + "\n" if context_value else "") + f"Purpose: {purpose}"
        if context_value:
            payload["context"] = context_value

        resp = self._request("POST", "/translate", data=payload)
        if resp.status_code == 456:
            raise QuotaExceeded("DeepL character limit reached.")
        if resp.status_code == 403:
            raise ValueError("Authentication failed during translation.")
        if resp.status_code == 400 and context_value:
            # Retry without context if the API does not accept it
            payload.pop("context", None)
            resp = self._request("POST", "/translate", data=payload)
        resp.raise_for_status()
        translations = resp.json().get("translations", [])
        if not translations:
            raise RuntimeError("No translation returned by DeepL.")
        return translations[0].get("text", "")

    def describe(self) -> str:
        tier = "Free" if self.base_url.endswith("api-free.deepl.com/v2") else "Pro"
        return f"DeepL ({tier})"


class LibreTranslateService(TranslationService):
    def __init__(self):
        import requests

        self.requests = requests
        self.base_url = "https://libretranslate.de"
        self.supports_context = False
        self.name = "LibreTranslate (public demo)"

    def available_languages(self, role: str) -> List[Dict[str, str]]:  # role unused
        resp = self.requests.get(f"{self.base_url}/languages", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        languages = [{"code": item["code"].upper(), "name": item.get("name", item["code"]) } for item in data]
        languages.sort(key=lambda x: x["name"].lower())
        return languages

    def translate(self, text: str, source_lang: Optional[str], target_lang: str, context: Optional[str] = None, purpose: Optional[str] = None) -> str:
        payload = {
            "q": text,
            "target": target_lang,
            "format": "text",
            "source": source_lang or "auto",
        }
        resp = self.requests.post(f"{self.base_url}/translate", data=payload, timeout=20)
        if resp.status_code == 429:
            raise QuotaExceeded("LibreTranslate rate limit reached.")
        resp.raise_for_status()
        data = resp.json()
        return data.get("translatedText", "")

    def describe(self) -> str:
        return self.name


def prompt_api_service() -> TranslationService:
    deepl_info = (
        "Enter your DeepL API key. Get one at https://www.deepl.com/account/summary.\n"
        "Leave blank to use the free LibreTranslate demo service instead."
    )
    while True:
        print(deepl_info)
        api_key = input("DeepL API key: ").strip()
        if not api_key:
            print("Using LibreTranslate (no key required). Note that this service is rate limited.")
            return LibreTranslateService()
        service = DeepLService(api_key)
        try:
            usage = service.check_usage()
        except Exception as exc:  # broad to allow loop
            print(f"Could not validate the API key: {exc}")
            retry = input("Try another key? [y/N]: ").strip().lower()
            if retry == "y":
                continue
            print("Falling back to LibreTranslate.")
            return LibreTranslateService()
        limit = usage.get("character_limit")
        used = usage.get("character_count")
        remaining = limit - used if limit is not None and used is not None else None
        print(f"Usage: {used} of {limit} characters used." if limit is not None else f"Usage: {used} characters used.")
        if remaining is not None:
            print(f"Remaining characters: {remaining}")
        confirm = input(f"Detected {service.describe()}. Is this your account? [Y/n]: ").strip().lower()
        if confirm not in ("", "y", "yes"):
            continue
        return service


def list_csv_files(input_dir: str) -> List[str]:
    if not os.path.exists(input_dir):
        os.makedirs(input_dir, exist_ok=True)
    files = [f for f in os.listdir(input_dir) if f.lower().endswith(".csv")]
    files.sort()
    return files


def choose_from_list(prompt: str, options: List[str]) -> int:
    while True:
        print(prompt)
        for idx, option in enumerate(options, start=1):
            print(f"[{idx}] {option}")
        choice = input("Enter the number: ").strip()
        if not choice.isdigit():
            print("Please enter a valid number.")
            continue
        index = int(choice)
        if 1 <= index <= len(options):
            return index - 1
        print("Choice out of range. Try again.")


def prompt_language(service: TranslationService, role: str) -> Optional[str]:
    languages = service.available_languages(role)
    code_lookup = {lang["code"].upper(): lang for lang in languages}
    name_lookup = {lang["name"].lower(): lang for lang in languages}

    while True:
        value = input(f"Enter the {role} language code (or 'auto' to detect, 'help' for list): ").strip()
        if value.lower() == "help":
            print("Available languages:")
            for lang in languages:
                print(f"- {lang['name']} - {lang['code']}")
            continue
        if value == "":
            if role == "source":
                return None
        if value.lower() == "auto" and role == "source":
            return None
        lang = code_lookup.get(value.upper()) or name_lookup.get(value.lower())
        if lang:
            return lang["code"].upper()
        print("Invalid language. Type 'help' to see options.")


def present_settings(file_name: str, source_col: str, target_col: str, context_col: Optional[str], purpose: Optional[str], source_lang: Optional[str], target_lang: str, rows_to_translate: int, service: TranslationService):
    print("\nSettings overview:")
    print(f"File: {file_name}")
    print(f"Source column: {source_col}")
    print(f"Output column: {target_col}")
    if context_col:
        print(f"Context column: {context_col}")
    if purpose:
        print(f"Purpose: {purpose}")
    print(f"Source language: {source_lang or 'Auto-detect'}")
    print(f"Target language: {target_lang}")
    print(f"Rows to translate: {rows_to_translate}")
    print(f"Translator: {service.describe()}")


class TranslationRun:
    def __init__(
        self,
        df,
        source_col: str,
        target_col: str,
        context_col: Optional[str],
        purpose: Optional[str],
        service: TranslationService,
        source_lang: Optional[str],
        target_lang: str,
    ):
        self.df = df
        self.source_col = source_col
        self.target_col = target_col
        self.context_col = context_col
        self.purpose = purpose
        self.service = service
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.successes: List[Tuple[int, str, str]] = []
        self.failures: List[Tuple[int, str, str]] = []

    def _needs_translation(self, value) -> bool:
        if value is None:
            return True
        if hasattr(value, "__float__"):
            try:
                import math

                if math.isnan(float(value)):
                    return True
            except Exception:
                pass
        text = str(value).strip()
        return text == ""

    def run(self) -> None:
        from tqdm import tqdm
        from colorama import Fore, Style, init as colorama_init

        colorama_init()
        translatable_rows = [i for i, val in self.df[self.target_col].items() if self._needs_translation(val)]
        progress = tqdm(total=len(translatable_rows), desc="Translating", unit="row")
        for idx in translatable_rows:
            source_text = str(self.df.at[idx, self.source_col])
            context_value = None
            if self.context_col and self.service.supports_context:
                context_piece = self.df.at[idx, self.context_col]
                if context_piece is not None:
                    context_value = str(context_piece)
            try:
                translation = self.service.translate(
                    text=source_text,
                    source_lang=self.source_lang,
                    target_lang=self.target_lang,
                    context=context_value,
                    purpose=self.purpose,
                )
                self.df.at[idx, self.target_col] = translation
                self.successes.append((idx, source_text, translation))
                recent = f"{Fore.GREEN}{translation}{Style.RESET_ALL}"
                progress.set_postfix_str(recent[:60])
            except QuotaExceeded as exc:
                progress.close()
                print(f"\n{Fore.RED}{exc}{Style.RESET_ALL}")
                action = input("(r)etry, (f)allback to LibreTranslate, or (s)top? ").strip().lower()
                if action == "f":
                    self.service = LibreTranslateService()
                    print("Switched to LibreTranslate for the remaining rows.")
                elif action == "s":
                    break
                progress = tqdm(total=len(translatable_rows) - len(self.successes), desc="Translating", unit="row")
                continue
            except Exception as exc:
                failure_message = f"Failed: {exc}"
                self.failures.append((idx, source_text, str(exc)))
                recent = f"{Fore.RED}{failure_message}{Style.RESET_ALL}"
                progress.set_postfix_str(recent[:60])
            finally:
                progress.update(1)
        progress.close()



def main():
    ensure_dependencies()
    import pandas as pd

    clear_console()
    print("CSV Translator with DeepL")
    service = prompt_api_service()

    input_dir = "CSVs"
    files = list_csv_files(input_dir)
    if not files:
        print(f"No CSV files found in '{input_dir}'. Please add files and retry.")
        sys.exit(0)

    file_index = choose_from_list("Choose a CSV file to translate:", files)
    file_name = files[file_index]
    file_path = os.path.join(input_dir, file_name)
    df = pd.read_csv(file_path)

    if df.empty:
        print("Selected CSV is empty. Nothing to translate.")
        sys.exit(0)

    columns = list(df.columns)
    col_index = choose_from_list("Select the source column (text to translate):", columns)
    source_col = columns[col_index]

    target_index = choose_from_list("Select the output column (where translations go):", columns)
    target_col = columns[target_index]

    context_col = None
    if service.supports_context:
        remaining_cols = [c for c in columns if c not in {source_col, target_col}]
        if remaining_cols:
            use_context = input("Choose a context column? [y/N]: ").strip().lower() == "y"
            if use_context:
                ctx_index = choose_from_list("Select the context column:", remaining_cols)
                context_col = remaining_cols[ctx_index]
    else:
        print(f"{service.describe()} does not support context columns; skipping this step.")

    purpose = None
    if service.supports_context:
        purpose_input = input("Describe the translation purpose (optional): ").strip()
        purpose = purpose_input if purpose_input else None

    print("\nLanguage selection:")
    source_lang = prompt_language(service, "source")
    target_lang = prompt_language(service, "target")

    rows_to_translate = sum(1 for v in df[target_col] if pd.isna(v) or str(v).strip() == "")
    present_settings(file_name, source_col, target_col, context_col, purpose, source_lang, target_lang, rows_to_translate, service)
    proceed = input("Proceed with translation? [Y/n]: ").strip().lower()
    if proceed not in ("", "y", "yes"):
        print("Translation cancelled.")
        sys.exit(0)

    run = TranslationRun(df, source_col, target_col, context_col, purpose, service, source_lang, target_lang)
    run.run()

    os.makedirs("Output", exist_ok=True)
    output_path = os.path.join("Output", file_name)
    df.to_csv(output_path, index=False)

    print("\nTranslation completed.")
    print(f"Saved translated CSV to: {output_path}")
    print(f"Successful translations: {len(run.successes)}")
    print(f"Failed translations: {len(run.failures)}")
    remaining = sum(1 for v in df[target_col] if pd.isna(v) or str(v).strip() == "")
    print(f"Remaining blank translations: {remaining}")

    if run.failures:
        print("\nFailures:")
        for idx, source, err in run.failures:
            print(f"- Row {idx}: {err}")

    detailed = input("Show detailed summary of translations? [y/N]: ").strip().lower() == "y"
    if detailed:
        for idx, source, translation in run.successes:
            print(f"Row {idx}: {source} -> {translation}")

    print_entire = input("Print entire translated CSV here? [y/N]: ").strip().lower() == "y"
    if print_entire:
        with pd.option_context('display.max_rows', None, 'display.max_columns', None):
            print(df)


if __name__ == "__main__":
    main()
