## Recommended Method: Use `marker` CLI for Bulk Conversion

Install `marker-pdf`:

```
pip install marker-pdf
```

### Convert a Whole Folder of PDFs

Run this command to convert all PDFs in a directory:

```
marker /path/to/pdf_folder /path/to/output_folder --workers 4 --batch_multiplier 2
```

- `--workers`: Number of parallel processes (adjust based on CPU/GPU).
    
- `--batch_multiplier`: Increases batch size if you have extra VRAM (speeds up conversion).
    
- Output: One `.md` file per PDF, saved in the output folder. 
    

### Example Script for Automation

```
import os
from marker.convert import convert_all

pdf_folder = "pdfs/"
output_folder = "markdown/"
os.makedirs(output_folder, exist_ok=True)

# Convert all PDFs in folder
convert_all(pdf_folder, output_folder, workers=4)
print("✅ All PDFs converted to Markdown!")
```

## 🔧 Optional: Smart Batch Tool with Fallbacks

For better reliability (e.g., mixing scanned and text-based PDFs), use **[smart-pdf-md](https://github.com/supermarsx/smart-pdf-md)**:

```
python smart-pdf-md.py ./pdfs 40 -m marker -o ./md_out --output-format md
```

- Automatically detects text-based vs. scanned PDFs.
    
- Uses fast extraction when possible, falls back to `marker` for complex docs. 
    
