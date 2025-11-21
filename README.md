# CSV Translator

A command-line helper to translate CSV files using DeepL when an API key is available, with Google Translate as a fallback. The tool asks which columns to use, counts how many rows need work, shows color-coded progress, and saves the result to a new CSV. Optionally copies the translated file to your clipboard.

## Features
- Prompts for DeepL API key (and explains where to get one) with a zero-config Google Translate fallback.
- Lets you choose source, target, and optional context columns.
- Supports auto-detect for the source language, and custom target language codes.
- Shows per-row success/failure with colorized output.
- Skips rows that already have a value in the target column.
- Writes a new `<name>_translated.csv` file and can copy it to your clipboard.

## Requirements
Install dependencies (preferably inside a virtual environment):

```bash
pip install -r requirements.txt
```

## Usage
1. Place the CSV you want to translate in the project folder.
2. Run the translator:
   ```bash
   python csv_translator.py
   ```
3. Follow the prompts:
   - Enter a DeepL API key or press Enter to continue without one (https://www.deepl.com/pro-api to get a key).
   - Provide the CSV filename.
   - Select the source column and language (or choose `auto`).
   - Enter or confirm the target column and desired target language.
   - (Optional) choose a context column to give the translator more detail per row.
4. Watch the progress indicators (green for success, red for failure). When finished, the tool reports totals and writes a new CSV alongside your original file.
5. If you choose, the script will copy the translated CSV contents to your clipboard (requires `pyperclip`).

> Note: If neither DeepL nor Google Translate dependencies are available, the script will exit with an instruction to install them via `requirements.txt`.
