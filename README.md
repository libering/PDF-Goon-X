# PDF-Goon X

A Python CLI tool and library for extracting high-quality images from PDF files. It intelligently decides whether to extract embedded images directly or render pages at calculated DPI, depending on the page content.

## Origin

This project is based on the original **PDF-Goon** tool by **Dnkz**, shared on the E-Hentai Forums:

> https://forums.e-hentai.org/index.php?showtopic=293338

PDF-Goon X is a refactored, modular rewrite of the original single-file script into a proper pip-installable Python package with clean module boundaries, type safety, and testability.

## Features

- Extracts raw embedded images from PDFs using Poppler's `pdfimages`
- Renders full-page layouts via `pdftocairo` when direct extraction isn't viable (multiple overlapping images, small icons, tricky color spaces like CMYK/DeviceN)
- Automatic DPI calculation based on embedded image dimensions
- Lossless image optimization (pingo on Windows, oxipng/jpegoptim on Linux)
- Recursive directory scanning for batch processing
- Moves processed PDFs to trash or a `!delete` folder
- Usable both as a CLI tool and as a Python library

## Requirements

- **Python** >= 3.11
- **Poppler-utils**: `pdfimages`, `pdfinfo`, `pdftocairo` (required)
- **pingo.exe** (Windows) or **oxipng** / **jpegoptim** (Linux/macOS) for lossless optimization (optional)

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Usage

### CLI

```bash
# Process PDFs in current directory
pdf-goon

# Process a specific directory
pdf-goon /path/to/pdfs

# Verbose output with per-page details
pdf-goon -v

# Move processed PDFs to trash
pdf-goon -r

# Recursive subdirectory scanning
pdf-goon -recursive

# Custom DPI for text-heavy pages (default: 400)
pdf-goon -dpi-text 600

# Ignore images narrower than N pixels (default: 500)
pdf-goon -min-w 300

# Disable lossless optimization
pdf-goon --no-optimization

# Debug mode (shows Poppler warnings + verbose)
pdf-goon --debug
```

### Python Library

```python
import pdf_goon

results = pdf_goon.process(
    path="./my-pdfs",
    verbose=True,
    dpi_text=400,
    optimize=True,
)

for result in results:
    if result.success:
        print(f"✓ {result.pdf_path} — {result.pages_processed} pages")
    else:
        print(f"✗ {result.pdf_path} — {result.error}")
```

## Development

```bash
# Run tests
pytest

# Type check
mypy pdf_goon

# Lint
ruff check pdf_goon tests

# Format
ruff format pdf_goon tests
```

## License

MIT
