"""Command-line CSV translator using DeepL or Google Translate fallback.
"""
import csv
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

try:
    import deepl
except ImportError:  # noqa: W0702 - optional dependency
    deepl = None

try:
    from deep_translator import GoogleTranslator
except ImportError:  # noqa: W0702 - optional dependency
    GoogleTranslator = None

try:
    import pyperclip
except ImportError:  # noqa: W0702 - optional dependency
    pyperclip = None

try:
    from colorama import Fore, Style, init as colorama_init
except ImportError:  # noqa: W0702 - optional dependency
    Fore = Style = None
    def colorama_init(*_args, **_kwargs):  # type: ignore[return-value]
        return None


def colored(text: str, color: Optional[str]) -> str:
    if color is None:
        return text
    return f"{color}{text}{Style.RESET_ALL}"


class TranslationClient:
    """Wrapper around DeepL with Google Translate fallback."""

    def __init__(self, api_key: Optional[str], source_lang: str, target_lang: str) -> None:
        self.api_key = api_key.strip() if api_key else ""
        self.source_lang = source_lang.upper() if source_lang.lower() != "auto" else "auto"
        self.target_lang = target_lang.upper()
        self.deepl_client = None
        if self.api_key and deepl:
            try:
                self.deepl_client = deepl.Translator(self.api_key)
            except Exception as exc:  # pragma: no cover - runtime error handling
                print(colored(f"Could not initialize DeepL: {exc}", Fore.RED if Fore else None))
        elif self.api_key and not deepl:
            print(colored("DeepL SDK not installed; falling back to Google Translate.", Fore.YELLOW if Fore else None))

        if not self.deepl_client and not GoogleTranslator:
            sys.exit("Neither DeepL nor deep-translator (Google) is available. Install dependencies from requirements.txt.")

    def translate(self, text: str, context: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        if not text.strip():
            return text, None
        cleaned_source = None if self.source_lang == "AUTO" else self.source_lang
        try:
            if self.deepl_client:
                result = self.deepl_client.translate_text(
                    text,
                    source_lang=cleaned_source,
                    target_lang=self.target_lang,
                    context=context,
                )
                return result.text, None
            translator = GoogleTranslator(source=self.source_lang if self.source_lang != "AUTO" else "auto", target=self.target_lang.lower())
            translated_text = translator.translate(text)
            return translated_text, None
        except Exception as exc:  # pragma: no cover - runtime error handling
            return None, str(exc)


def prompt_path() -> Path:
    print("Place your CSV in the current folder and enter its filename (e.g., data.csv).")
    while True:
        filename = input("CSV filename: ").strip()
        path = Path(filename)
        if path.exists() and path.suffix.lower() == ".csv":
            return path
        print(colored("File not found or not a CSV. Try again.", Fore.RED if Fore else None))


def prompt_column(columns: List[str], prompt_text: str) -> str:
    print(prompt_text)
    for idx, name in enumerate(columns):
        print(f"  [{idx}] {name}")
    while True:
        answer = input("Choose by name or index: ").strip()
        if answer.isdigit() and 0 <= int(answer) < len(columns):
            return columns[int(answer)]
        if answer in columns:
            return answer
        print(colored("Invalid selection. Try again.", Fore.RED if Fore else None))


def prompt_language(prompt_text: str, allow_auto: bool = False) -> str:
    suffix = " or 'auto'" if allow_auto else ""
    while True:
        choice = input(f"{prompt_text} (e.g., EN, DE, ES{suffix}): ").strip()
        if allow_auto and choice.lower() == "auto":
            return "auto"
        if choice:
            return choice
        print(colored("Please enter a language code.", Fore.RED if Fore else None))


def read_csv_rows(path: Path) -> Tuple[List[str], List[dict]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            sys.exit("CSV has no header row.")
        rows = list(reader)
    return reader.fieldnames, rows


def count_pending(rows: Iterable[dict], source_col: str, target_col: str) -> int:
    pending = 0
    for row in rows:
        source = (row.get(source_col) or "").strip()
        target = (row.get(target_col) or "").strip()
        if source and not target:
            pending += 1
    return pending


def ensure_target_column(columns: List[str], target_col: str) -> List[str]:
    if target_col not in columns:
        return columns + [target_col]
    return columns


def write_csv(path: Path, columns: List[str], rows: List[dict]) -> Path:
    output_path = path.with_name(path.stem + "_translated" + path.suffix)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def copy_to_clipboard(path: Path) -> None:
    if not pyperclip:
        print(colored("pyperclip not installed; skipping clipboard copy.", Fore.YELLOW if Fore else None))
        return
    try:
        content = path.read_text(encoding="utf-8")
        pyperclip.copy(content)
        print(colored("CSV copied to clipboard.", Fore.GREEN if Fore else None))
    except Exception as exc:  # pragma: no cover - runtime error handling
        print(colored(f"Clipboard copy failed: {exc}", Fore.RED if Fore else None))


def main() -> None:
    colorama_init(autoreset=True)
    print("CSV Translator (DeepL with Google Translate fallback)")
    print("If you need a DeepL API key, visit https://www.deepl.com/pro-api to create one.")
    print("Press Enter to continue without a key and use Google Translate instead.\n")

    api_key = input("Enter DeepL API key (or leave blank to skip): ")

    csv_path = prompt_path()
    columns, rows = read_csv_rows(csv_path)

    source_col = prompt_column(columns, "Select the source column (text to translate):")
    target_col_input = input("Name of the target column (existing or new): ").strip()
    target_col = target_col_input or "translation"
    columns = ensure_target_column(columns, target_col)
    target_col = prompt_column(columns, "Confirm the target column where translations will be saved:")
    source_lang = prompt_language("Source language code", allow_auto=True)
    target_lang = prompt_language("Target language code")

    context_col_answer = input("Is there a context column? Enter name or leave blank: ").strip()
    context_col = context_col_answer if context_col_answer in columns else None

    translator = TranslationClient(api_key=api_key, source_lang=source_lang, target_lang=target_lang)

    pending = count_pending(rows, source_col, target_col)
    print(colored(f"{pending} entries need translation (empty target cells).", Fore.CYAN if Fore else None))
    if pending == 0:
        print("Nothing to translate. Exiting.")
        return

    translated = 0
    failures = 0

    for idx, row in enumerate(rows, start=1):
        source_text = (row.get(source_col) or "").strip()
        current_target = (row.get(target_col) or "").strip()
        if not source_text or current_target:
            continue

        context_val = (row.get(context_col) or "").strip() if context_col else None
        result, error = translator.translate(source_text, context_val)

        if result is not None:
            row[target_col] = result
            translated += 1
            print(colored(f"[{idx}] ✅ {result}", Fore.GREEN if Fore else None))
        else:
            failures += 1
            print(colored(f"[{idx}] ❌ {error}", Fore.RED if Fore else None))

    output_path = write_csv(csv_path, ensure_target_column(columns, target_col), rows)
    print(colored("\nTranslation complete!", Fore.GREEN if Fore else None))
    print(f"Translated: {translated} | Failed: {failures} | Output: {output_path}")

    copy_choice = input("Copy the translated CSV to clipboard? (y/N): ").strip().lower()
    if copy_choice == "y":
        copy_to_clipboard(output_path)


if __name__ == "__main__":
    main()
