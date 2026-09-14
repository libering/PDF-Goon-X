"""Standalone render worker: renders a single PDF page via pypdfium2."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    """Entry point: parse args, render page, write PNG."""
    if len(sys.argv) != 5:
        sys.stderr.write(
            f"Usage: {sys.argv[0]} <pdf_path> <page_num> <dpi> <output_path>\n"
        )
        sys.exit(1)

    try:
        pdf_path = Path(sys.argv[1])
        page_num = int(sys.argv[2])
        dpi = float(sys.argv[3])
        output_path = Path(sys.argv[4])
    except (ValueError, TypeError) as exc:
        sys.stderr.write(f"Argument error: {exc}\n")
        sys.exit(1)

    try:
        import pypdfium2 as pdfium

        # Read bytes from disk to avoid Windows file lock sharing issues
        pdf_bytes = pdf_path.read_bytes()
        pdf = pdfium.PdfDocument(pdf_bytes)
        page = pdf[page_num - 1]
        bitmap = page.render(scale=dpi / 72.0)
        pil_image = bitmap.to_pil()
        pil_image.save(output_path)
    except Exception as exc:
        sys.stderr.write(f"Render error: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
