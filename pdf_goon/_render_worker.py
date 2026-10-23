"""Standalone render worker: renders PDF page(s) via pypdfium2 with memory management."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops


def _normalize_rendered_image(pil_image: Image.Image) -> Image.Image:
    """Normalize grayscale rendered pages from 24/32-bit to 8-bit mode L/LA without loss."""
    if pil_image.mode == "RGB":
        r, g, b = pil_image.split()
        if not ImageChops.difference(r, g).getbbox() and not ImageChops.difference(r, b).getbbox():
            converted = pil_image.convert("L")
            pil_image.close()
            return converted
    elif pil_image.mode == "RGBA":
        r, g, b, _ = pil_image.split()
        if not ImageChops.difference(r, g).getbbox() and not ImageChops.difference(r, b).getbbox():
            converted = pil_image.convert("LA")
            pil_image.close()
            return converted
    return pil_image


def _render_single_page_to_file(
    pdf: Any, page_num: int, dpi: float, output_path: Path
) -> None:
    """Render a single page, normalize color space, and deterministically free C memory."""
    page = pdf[page_num - 1]
    bitmap: Any = None
    pil_image: Any = None
    try:
        bitmap = page.render(scale=dpi / 72.0)
        pil_image = bitmap.to_pil()
        normalized_img = _normalize_rendered_image(pil_image)
        normalized_img.save(output_path)
        if normalized_img is not pil_image and hasattr(normalized_img, "close"):
            normalized_img.close()
    finally:
        if pil_image is not None and hasattr(pil_image, "close"):
            try:
                pil_image.close()
            except Exception:
                pass
        if bitmap is not None and hasattr(bitmap, "close"):
            try:
                bitmap.close()
            except Exception:
                pass
        if hasattr(page, "close"):
            try:
                page.close()
            except Exception:
                pass


def run_batch_render(pdf_path: Path, tasks: list[dict]) -> None:
    """Load PDF document once with pypdfium2 and render all requested pages sequentially."""
    import pypdfium2 as pdfium

    pdf_bytes = pdf_path.read_bytes()
    pdf = pdfium.PdfDocument(pdf_bytes)
    had_error = False
    try:
        for task in tasks:
            page_num = int(task["page"])
            dpi = float(task["dpi"])
            output_path = Path(task["out"])
            try:
                _render_single_page_to_file(pdf, page_num, dpi, output_path)
            except Exception as e:
                had_error = True
                sys.stderr.write(f"Error rendering page {page_num}: {e}\n")
    finally:
        pdf.close()
    if had_error:
        sys.exit(1)


def _handle_batch_worker(args: list[str]) -> None:
    """Parse tasks and execute batch render mode."""
    try:
        pdf_path = Path(args[1])
        tasks_arg = args[2]
        p = Path(tasks_arg)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                tasks = json.load(f)
        else:
            tasks = json.loads(tasks_arg)
        run_batch_render(pdf_path, tasks)
    except Exception as exc:
        sys.stderr.write(f"Batch render error: {exc}\n")
        sys.exit(1)
    sys.exit(0)


def _handle_single_page_worker(args: list[str]) -> None:
    """Parse args and execute single page render."""
    if len(args) != 4:
        sys.stderr.write(
            "Usage: _render_worker <pdf_path> <page_num> <dpi> <output_path>\n"
        )
        sys.exit(1)

    try:
        pdf_path = Path(args[0])
        page_num = int(args[1])
        dpi = float(args[2])
        output_path = Path(args[3])
    except (ValueError, TypeError) as exc:
        sys.stderr.write(f"Argument error: {exc}\n")
        sys.exit(1)

    try:
        import pypdfium2 as pdfium

        pdf_bytes = pdf_path.read_bytes()
        pdf = pdfium.PdfDocument(pdf_bytes)
        try:
            _render_single_page_to_file(pdf, page_num, dpi, output_path)
        finally:
            pdf.close()
    except Exception as exc:
        sys.stderr.write(f"Render error: {exc}\n")
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args, render page(s), write PNG."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 3 and args[0] == "--batch":
        _handle_batch_worker(args)
    else:
        _handle_single_page_worker(args)


if __name__ == "__main__":
    main()
