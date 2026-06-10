# Product: PDF-Goon

PDF-Goon is a CLI tool and Python library for extracting high-quality images from PDF files. It intelligently decides whether to extract embedded images directly or render pages at calculated DPI, depending on the page content.

## Key Capabilities

- Extracts raw embedded images from PDFs using Poppler's `pdfimages`
- Renders full-page layouts via `pdftocairo` when extraction isn't viable (multiple images, small icons, tricky color spaces like CMYK/DeviceN)
- Lossless image optimization (pingo on Windows, oxipng/jpegoptim on Linux)
- Recursive directory scanning for batch processing
- Moves processed PDFs to trash or a `!delete` folder
- Supports PyInstaller bundling for standalone distribution

## Target Platform

Primarily Windows (uses Windows Recycle Bin, pingo optimizer, ctypes shell operations). Linux/macOS supported with freedesktop trash and oxipng/jpegoptim.

## External Dependencies (Runtime)

- **Poppler-utils**: `pdfimages`, `pdfinfo`, `pdftocairo` (required)
- **pingo.exe** (Windows) or **oxipng**/**jpegoptim** (Linux) for lossless optimization (optional)
