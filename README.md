# PDF-Goon X

A Python CLI tool and library for extracting high-quality images from PDF files. It intelligently decides whether to extract embedded images directly or render pages at calculated DPI, depending on the page content.

## Origin

Based on the original **PDF-Goon** by **Dnkz** (E-Hentai Forums):
> https://forums.e-hentai.org/index.php?showtopic=293338

PDF-Goon X is a modular rewrite into a pip-installable Python package with type safety and testability.

## Why PDF-Goon?

Existing PDF image extraction tools each have a fundamental limitation:

| Approach | Problem |
|----------|---------|
| `pdfimages` alone | Fragments complex layouts — multiple images or text+image pages get torn apart |
| `pdftocairo` alone | Re-encodes everything, causing unnecessary quality loss on pages that are just one big image |
| Adobe Acrobat export | Paid software, manual per-page operation, not scriptable |
| Online converters | Privacy risk, unpredictable quality, no batch processing |

PDF-Goon solves this with **per-page intelligent decision-making**: extract the raw image when the page is just one image, render the full page when the layout calls for it.

## Features

- **Smart extraction** — Extracts raw embedded images via `pypdf` when possible (zero quality loss)
- **Page coverage check** — Only extracts when the image truly fills the page; pages with margins are rendered instead
- **Automatic rendering** — Renders full-page layouts via `pypdfium2` when extraction isn't viable (multiple images, small icons, CMYK color spaces, text content)
- **DPI calculation** — Automatically determines optimal rendering DPI from embedded image dimensions
- **Blank page detection** — Skips pages with no images and no text (configurable via `--keep-blank`)
- **Lossless optimization** — pingo (Windows) / oxipng+jpegoptim (Linux), optional
- **Batch processing** — Recursive directory scanning with progress reporting
- **PDF cleanup** — Moves processed PDFs to system trash or `!delete` folder
- **Backend protocol** — Pluggable analysis/extraction/rendering backends for future engine swaps
- **Dual interface** — Usable as CLI tool and Python library

## Requirements

| Dependency | Required | Notes |
|-----------|----------|-------|
| Python >= 3.11 | Yes | |
| pypdf >= 5.0 | Yes | Installed automatically via pip |
| pypdfium2 >= 4.0 | Yes | Installed automatically via pip |
| Pillow >= 10.0 | Yes | Installed automatically via pip |
| pingo (Windows) | No | Lossless optimization, optional |
| oxipng / jpegoptim (Linux) | No | Lossless optimization, optional |

## Installation

```bash
# From source
pip install -e .

# Development (includes pytest, hypothesis, mypy, ruff)
pip install -e ".[dev]"
```

## Usage

### CLI

```bash
# Process all PDFs in current directory
pdf-goon

# Process a specific file or directory
pdf-goon "C:\path\to\file.pdf"
pdf-goon /path/to/pdfs/

# Verbose — show per-page extraction/rendering decisions
pdf-goon -v

# Move processed PDFs to trash after extraction
pdf-goon -r

# Recursively scan subdirectories
pdf-goon -recursive

# Custom DPI for text-heavy/icon-only pages (default: 400)
pdf-goon -dpi-text 600

# Minimum width threshold — images narrower than this trigger rendering (default: 500px)
pdf-goon -min-w 300

# Keep blank pages (render instead of skip)
pdf-goon --keep-blank

# Disable lossless optimization
pdf-goon --no-optimization

# Debug mode (all warnings + verbose output)
pdf-goon --debug
```

### CLI Options Reference

| Flag | Default | Description |
|------|---------|-------------|
| `path` | `.` | Target file or directory |
| `-v`, `--verbose` | off | Per-page processing details |
| `-r`, `--replace` | off | Move processed PDF to trash/!delete |
| `-recursive` | off | Include subdirectories |
| `-dpi-text DPI` | 400 | Rendering DPI for text/icon pages |
| `-min-w PX` | 500 | Min image width for direct extraction |
| `--keep-blank` | off | Render blank pages instead of skipping |
| `--no-optimization` | off | Skip lossless compression |
| `--debug` | off | Show all warnings (implies -v) |

### Python Library

```python
import pdf_goon

# Basic usage
results = pdf_goon.process("./my-pdfs")

# Full options
results = pdf_goon.process(
    path="./my-pdfs",
    verbose=True,
    replace=False,
    optimize=True,
    dpi_text=400,
    min_width=500,
    recursive=True,
    force_render=False,
    debug=False,
    progress_callback=lambda current, total, path: print(f"[{current}/{total}] {path.name}"),
)

# Check results
for result in results:
    if result.success:
        print(f"OK {result.pdf_path.name} — {result.pages_processed} pages")
    else:
        print(f"FAIL {result.pdf_path.name} — {result.error}")
```

## How It Works

For each page in a PDF, the tool decides between three modes:

### EXTRACT mode
- Triggered when the page has a **single image** that:
  - Is wider than `min_width`
  - Uses a standard color space (RGB/Gray)
  - Has no text content
  - **Truly fills the page** (>= 95% coverage in both dimensions)
- Uses `pypdf` to extract the raw embedded image losslessly
- Output: original format (PNG/JPEG) as embedded in the PDF

### RENDER mode
- Triggered when:
  - Page has **multiple images** (complex layout)
  - Image is **too small** (likely an icon, not full-page art)
  - Image uses **tricky color space** (CMYK, DeviceN, Separation)
  - Image **doesn't fill the page** (has margins/background)
  - Image is **rotated** relative to the page
  - No images detected (text-only page)
- Uses `pypdfium2` to render the page at calculated DPI
- DPI is derived from the largest embedded image dimensions, or falls back to `-dpi-text`
- Output: PNG rendering of the full page

### BLANK mode
- Triggered when the page has **no images and no text**
- Skipped by default (no output file)
- Use `--keep-blank` to render blank pages at `dpi-text` instead

### Output naming

```
output_dir/
├── 001.png          # Page 1, extracted (EXTRACT mode)
├── 002_r.png        # Page 2, rendered (RENDER mode, "_r" tag)
├── 003.jpg          # Page 3, extracted JPEG
├── 004_001.png      # Page 4, first sub-image (multiple images extracted)
├── 004_002.png      # Page 4, second sub-image
└── ...
```

## Development

```bash
# Run tests
pytest

# Type checking
mypy pdf_goon

# Lint + format
ruff check pdf_goon tests
ruff format pdf_goon tests
```

## Project Structure

```
pdf_goon/
├── __init__.py          # Public API: process()
├── models.py            # Dataclasses, enums, constants, exceptions
├── cli.py               # CLI layer: argparse → Config → process()
├── core.py              # Orchestration: batch processing, per-page pipeline
├── analyze.py           # PDF inspection: page count, image metadata, mode decisions
├── extract.py           # Image extraction (pypdf) and page rendering (pypdfium2 worker)
├── _render_worker.py     # Standalone render worker subprocess (pypdfium2)
├── backends.py          # Pluggable backend protocol definitions
├── files.py             # File operations: unique paths, trash, temp workspace
├── optimize.py          # Lossless image optimization
├── tools.py             # Tool resolution, subprocess execution
```

## License

MIT
