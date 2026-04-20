find /home/peter/health-libraries/user-health -type f -name "*.pdf" -print0 | while IFS= read -r -d '' file; do
  ebook-convert "$file" "${file%.pdf}.txt" --enable-heuristics --html-unwrap-factor 0.2
doneCopied!
