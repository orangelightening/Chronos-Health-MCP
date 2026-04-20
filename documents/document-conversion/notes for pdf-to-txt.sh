Key considerations for automation:

Installation: Ensure Calibre is installed via sudo apt install calibre before running the script.
Heuristics: The --enable-heuristics flag is critical for guessing paragraph structures and removing unnecessary hyphens, while --html-unwrap-factor helps control line breaks.
Limitations: Calibre cannot extract text from image-only or scanned PDFs; for those, you must use OCR tools like OCRmyPDF first.
Batch Safety: The script includes a check if [ ! -e ... ] to prevent overwriting existing text files.
