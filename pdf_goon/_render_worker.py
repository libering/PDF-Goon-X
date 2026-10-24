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


MAX_RENDER_PIXELS: int = 100_000_000  # 100 megapixels (~400MB RGBA buffer)


def _close_safely(obj: Any) -> None:
    """Deterministically call close() on object if present, ignoring errors."""
    if obj is not None and hasattr(obj, "close"):
        try:
            obj.close()
        except Exception:
            pass


def _get_page_pts(page: Any) -> tuple[float, float]:
    """Extract width and height in points from page, falling back to 0.0."""
    if hasattr(page, "get_size"):
        try:
            size = page.get_size()
            if isinstance(size, (tuple, list)) and len(size) >= 2:
                return float(size[0]), float(size[1])
        except Exception:
            pass
    return 0.0, 0.0


def _render_standard_page(page: Any, scale: float, output_path: Path) -> None:
    """Render page directly via pypdfium2 without tiling and normalize color space."""
    bitmap: Any = None
    pil_image: Any = None
    try:
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        normalized_img = _normalize_rendered_image(pil_image)
        normalized_img.save(output_path)
        if normalized_img is not pil_image:
            _close_safely(normalized_img)
    finally:
        _close_safely(pil_image)
        _close_safely(bitmap)
        _close_safely(page)


MAX_CANVAS_PIXELS: int = 500_000_000  # 500 megapixels (Pillow limit defense against bombs)


def _render_single_page_to_file(
    pdf: Any,
    page_num: int,
    dpi: float,
    output_path: Path,
    force_tiles: bool = False,
) -> None:
    """Render single page: switches to tiled engine on large canvases or renders standard."""
    from pdf_goon.models import PageInfo
    from pdf_goon.render.tiler import render_page_tiled, should_tile_render

    page = pdf[page_num - 1]
    scale = max(0.5, min(dpi, 2400.0)) / 72.0
    w_pts, h_pts = _get_page_pts(page)
    if round(w_pts * scale) * round(h_pts * scale) > MAX_CANVAS_PIXELS:
        raise ValueError(
            f"Page {page_num} render dimensions exceed maximum limit of {MAX_CANVAS_PIXELS} pixels"
        )
    page_info = PageInfo(width_pts=w_pts, height_pts=h_pts)

    if w_pts > 0 and h_pts > 0 and should_tile_render(page_info, dpi, force_tiles=force_tiles):
        try:
            render_page_tiled(page, output_path, dpi, page_info)
        finally:
            _close_safely(page)
        return

    _render_standard_page(page, scale, output_path)


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
            force_tiles = bool(task.get("tiles", False))
            try:
                _render_single_page_to_file(
                    pdf, page_num, dpi, output_path, force_tiles=force_tiles
                )
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
    if len(args) not in (4, 5):
        sys.stderr.write(
            "Usage: _render_worker <pdf_path> <page_num> <dpi> <output_path> [--tiles]\n"
        )
        sys.exit(1)

    try:
        pdf_path = Path(args[0])
        page_num = int(args[1])
        dpi = float(args[2])
        output_path = Path(args[3])
        force_tiles = len(args) == 5 and args[4] in ("--tiles", "tiles", "True", "true")
    except (ValueError, TypeError) as exc:
        sys.stderr.write(f"Argument error: {exc}\n")
        sys.exit(1)

    try:
        import pypdfium2 as pdfium

        pdf_bytes = pdf_path.read_bytes()
        pdf = pdfium.PdfDocument(pdf_bytes)
        try:
            _render_single_page_to_file(
                pdf, page_num, dpi, output_path, force_tiles=force_tiles
            )
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
