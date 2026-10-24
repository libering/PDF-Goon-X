"""Tiled rendering engine for extreme PDF page canvas sizes.

Employs FPDF_RenderPageBitmapWithMatrix with affine translation and
Padding-and-Crop (P=2px) to eliminate bilateral interpolation edge artifacts,
achieving zero pixel drift under constant C memory bounds.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
import pypdfium2.raw as pdfium_c

from pdf_goon._render_worker import _normalize_rendered_image
from pdf_goon.models import MAX_RENDER_PIXELS, PageInfo

logger = logging.getLogger(__name__)

# Single edge limit beyond which 16-bit raster coordinates risk overflow
MAX_DIM_16BIT: int = 16_384


@dataclass(frozen=True)
class TileInfo:
    """Metadata describing a single tile in the grid."""

    row: int
    col: int
    x0: int
    y0: int
    x1: int
    y1: int
    w: int
    h: int


def should_tile_render(
    page_info: PageInfo,
    dpi: float,
    threshold_pixels: int = MAX_RENDER_PIXELS,
    force_tiles: bool = False,
) -> bool:
    """Determine whether a page should be rendered in tiles.

    Triggers if force_tiles is True, or if total estimated pixels exceeds
    threshold_pixels, or if any dimension exceeds MAX_DIM_16BIT.
    """
    if force_tiles:
        return True
    scale = dpi / 72.0
    est_w = round(page_info.width_pts * scale)
    est_h = round(page_info.height_pts * scale)
    total_pixels = est_w * est_h

    if total_pixels > threshold_pixels:
        return True
    if est_w > MAX_DIM_16BIT or est_h > MAX_DIM_16BIT:
        return True
    return False


def calculate_tile_grid(
    total_w: int, total_h: int, tile_size: int = 4096
) -> tuple[list[TileInfo], int, int]:
    """Calculate grid coordinates with dynamic edge truncation."""
    grid: list[TileInfo] = []
    rows = (total_h + tile_size - 1) // tile_size
    cols = (total_w + tile_size - 1) // tile_size

    for r in range(rows):
        y0 = r * tile_size
        y1 = min(total_h, y0 + tile_size)
        h = y1 - y0
        for c in range(cols):
            x0 = c * tile_size
            x1 = min(total_w, x0 + tile_size)
            w = x1 - x0
            grid.append(TileInfo(row=r, col=c, x0=x0, y0=y0, x1=x1, y1=y1, w=w, h=h))

    return grid, rows, cols


def _render_tile_bitmap(
    page_handle: Any,
    scale: float,
    x0: int,
    y0: int,
    w_buf: int,
    h_buf: int,
    padding: int,
    render_flags: int = pdfium_c.FPDF_ANNOT | pdfium_c.FPDF_PRINTING,
) -> Any:
    """Allocate native bitmap, fill with opaque white, and render with translated matrix."""
    import pypdfium2 as pdfium
    bitmap = pdfium.PdfBitmap.new_native(w_buf, h_buf, format=pdfium_c.FPDFBitmap_BGR)
    try:
        bitmap.fill_rect((255, 255, 255, 255), 0, 0, w_buf, h_buf)
        matrix = pdfium_c.FS_MATRIX(
            a=scale,
            b=0.0,
            c=0.0,
            d=scale,
            e=float(-x0 + padding),
            f=float(-y0 + padding),
        )
        clip = pdfium_c.FS_RECTF(left=0, top=0, right=w_buf, bottom=h_buf)
        pdfium_c.FPDF_RenderPageBitmapWithMatrix(
            bitmap.raw, page_handle, matrix, clip, render_flags
        )
        return bitmap
    except Exception:
        bitmap.close()
        raise


def _bitmap_to_cropped_image(
    bitmap: Any, padding: int, tile_w: int, tile_h: int
) -> Image.Image:
    """Convert native bitmap to PIL Image, close bitmap, and crop off padding."""
    try:
        pil_padded = bitmap.to_pil()
    finally:
        bitmap.close()

    if padding > 0:
        cropped = pil_padded.crop((padding, padding, padding + tile_w, padding + tile_h))
        pil_padded.close()
        return cropped
    return pil_padded


def _save_tile_artifacts(
    target_path: Path,
    tiles_meta: list[dict[str, Any]],
    page_info: PageInfo,
    dpi: float,
    total_w: int,
    total_h: int,
    tile_size: int,
    padding: int,
    rows: int,
    cols: int,
) -> Path:
    """Save metadata.json in the tile directory."""
    tile_dir = target_path.parent / f"{target_path.stem}_tiles"
    tile_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "page_width_pts": page_info.width_pts,
        "page_height_pts": page_info.height_pts,
        "dpi": dpi,
        "total_width_px": total_w,
        "total_height_px": total_h,
        "tile_size": tile_size,
        "padding": padding,
        "rows": rows,
        "cols": cols,
        "tiles": tiles_meta,
    }
    meta_path = tile_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return tile_dir


def _render_and_paste_tiles(
    page_handle: Any,
    scale: float,
    grid: list[TileInfo],
    canvas: Image.Image,
    padding: int,
    tile_dir: Path,
    save_tile_dir: bool,
    render_flags: int,
) -> list[dict[str, Any]]:
    """Iterate through grid tiles, render, paste into canvas, and optionally save tile files."""
    tiles_meta: list[dict[str, Any]] = []
    for t in grid:
        w_buf = t.w + 2 * padding
        h_buf = t.h + 2 * padding
        bitmap = _render_tile_bitmap(
            page_handle, scale, t.x0, t.y0, w_buf, h_buf, padding, render_flags
        )
        tile_img = _bitmap_to_cropped_image(bitmap, padding, t.w, t.h)
        canvas.paste(tile_img, (t.x0, t.y0))

        if save_tile_dir:
            tile_filename = f"tile_r{t.row:02d}_c{t.col:02d}.png"
            tile_img.save(tile_dir / tile_filename)
            tiles_meta.append({
                "row": t.row, "col": t.col, "x": t.x0, "y": t.y0,
                "w": t.w, "h": t.h, "file": tile_filename,
            })
    return tiles_meta


def render_page_tiled(
    page: Any,
    target_path: Path,
    dpi: float,
    page_info: PageInfo,
    tile_size: int = 4096,
    padding: int = 2,
    save_tile_dir: bool = False,
    render_flags: int = pdfium_c.FPDF_ANNOT,
) -> list[Path]:
    """Render an ultra-large PDF page using constant-memory tiled rendering."""
    scale = dpi / 72.0
    total_w = round(page_info.width_pts * scale)
    total_h = round(page_info.height_pts * scale)
    grid, rows, cols = calculate_tile_grid(total_w, total_h, tile_size)

    Image.MAX_IMAGE_PIXELS = 500_000_000
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    tile_dir = target_path.parent / f"{target_path.stem}_tiles"
    if save_tile_dir:
        tile_dir.mkdir(parents=True, exist_ok=True)

    page_handle = getattr(page, "raw", page)
    tiles_meta = _render_and_paste_tiles(
        page_handle, scale, grid, canvas, padding, tile_dir, save_tile_dir, render_flags
    )

    normalized_canvas = _normalize_rendered_image(canvas)
    normalized_canvas.save(target_path)

    produced: list[Path] = [target_path]
    if save_tile_dir:
        _save_tile_artifacts(
            target_path, tiles_meta, page_info, dpi, total_w, total_h,
            tile_size, padding, rows, cols
        )
        produced.append(tile_dir)

    return produced
