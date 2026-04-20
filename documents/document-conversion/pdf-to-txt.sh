for file in *.pdf; do
  if [ ! -e "${file%.pdf}.txt" ]; then
    ebook-convert "$file" "${file%.pdf}.txt" --enable-heuristics --html-unwrap-factor 0.2
  fi
done
