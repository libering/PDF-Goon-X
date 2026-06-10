"""PDF inspection: page count, image metadata, page dimensions, and processing decisions."""

from __future__ import annotations

import contextlib
import logging
import re
import struct
from collections.abc import Callable
from pathlib import Path

from pdf_goon.models import (
    DPI_MAX,
    DPI_MIN,
    TRICKY_COLORS,
    ImageInfo,
    PageDecision,
    PageInfo,
    ProcessingMode,
    SubprocessError,
)
from pdf_goon.tools import get_tool_path, run_command

logger = logging.getLogger(__name__)


def get_page_count(pdf_path: Path, *, run: Callable[[list[str]], str] = run_command) -> int | None:
    """Return total page count, or None if PDF is unreadable."""
    try:
        output = run([get_tool_path("pdfinfo"), str(pdf_path)])
    except SubprocessError:
        return None

    match = re.search(r"Pages:\s+(\d+)", output)
    if not match:
        return None

    return int(match.group(1))


def get_image_data(
    pdf_path: Path,
    page_num: int,
    *,
    run: Callable[[list[str]], str] = run_command,
) -> tuple[list[ImageInfo], list[str]]:
    """Return (images, mask_indices) for a given page."""
    try:
        output = run([
            get_tool_path("pdfimages"),
            "-list",
            "-f", str(page_num),
            "-l", str(page_num),
            str(pdf_path),
        ])
    except SubprocessError:
        return [], []

    images: list[ImageInfo] = []
    mask_indices: list[str] = []
    img_idx = 0

    for line in output.strip().split("\n"):
        parts = line.split()
        if len(parts) < 13 or not parts[0].isdigit():
            continue

        is_mask = parts[2].lower() == "smask"
        if is_mask:
            mask_indices.append(str(img_idx).zfill(3))
        else:
            with contextlib.suppress(ValueError, IndexError):
                images.append(ImageInfo(
                    width=int(parts[3]),
                    height=int(parts[4]),
                    color=parts[5].lower(),
                    is_mask=False,
                ))

        img_idx += 1

    return images, mask_indices


def get_page_info(
    pdf_path: Path,
    page_num: int,
    *,
    run: Callable[[list[str]], str] = run_command,
) -> PageInfo:
    """Return physical page dimensions in points."""
    try:
        output = run([
            get_tool_path("pdfinfo"),
            "-f", str(page_num),
            "-l", str(page_num),
            str(pdf_path),
        ])
    except SubprocessError:
        return PageInfo(width_pts=0.0, height_pts=0.0)

    match = re.search(r"Page\s+(?:\d+\s+)?size:\s+([\d.]+)\s+x\s+([\d.]+)", output)
    if not match:
        return PageInfo(width_pts=0.0, height_pts=0.0)

    width = _to_c_float(match.group(1))
    height = _to_c_float(match.group(2))
    return PageInfo(width_pts=width, height_pts=height)


def decide_processing_mode(
    images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
    force_render: bool,
) -> PageDecision:
    """Determine whether to extract or render, and at what DPI."""
    if force_render:
        dpi = _clamp_dpi(float(dpi_text))
        return PageDecision(mode=ProcessingMode.RENDER, dpi=dpi, reason="Force render enabled")

    non_mask_images = [img for img in images if not img.is_mask]
    is_tricky = any(img.color in TRICKY_COLORS for img in non_mask_images)

    # Single non-mask image, not tricky color, wider than min_width → extract
    if len(non_mask_images) == 1 and not is_tricky:
        main_img = non_mask_images[0]
        if main_img.width > min_width:
            return PageDecision(mode=ProcessingMode.EXTRACT, dpi=0, reason="Single extractable image")

    # Otherwise → render
    dpi = _compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
    reason = _build_render_reason(non_mask_images, min_width, dpi_text)
    return PageDecision(mode=ProcessingMode.RENDER, dpi=dpi, reason=reason)


# --- Private helpers ---


def _to_c_float(value: str) -> float:
    """Simulate 32-bit C float precision via struct pack/unpack."""
    result: float = struct.unpack("f", struct.pack("f", float(value)))[0]
    return result


def _clamp_dpi(dpi: float) -> float:
    """Clamp DPI to [DPI_MIN, DPI_MAX]."""
    return max(DPI_MIN, min(DPI_MAX, dpi))


def _compute_render_dpi(
    images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
) -> float:
    """Calculate the best rendering DPI based on embedded image dimensions."""
    if not images:
        return _clamp_dpi(float(dpi_text))

    largest_width = max(img.width for img in images)

    if largest_width >= min_width and page_info.width_pts > 0:
        dpi = (largest_width * 72) / page_info.width_pts
    else:
        dpi = float(dpi_text)

    return _clamp_dpi(dpi)


def _build_render_reason(images: list[ImageInfo], min_width: int, dpi_text: int) -> str:
    """Build a human-readable reason string for render mode."""
    if not images:
        return f"No images, using fallback DPI {dpi_text}"

    largest_width = max(img.width for img in images)

    if len(images) > 1:
        return f"Multiple images ({len(images)}), rendering layout"

    if largest_width <= min_width:
        return f"Small image ({largest_width}px <= {min_width}px), likely icon"

    # Tricky color or other reason
    main_color = images[0].color if images else "unknown"
    if main_color in TRICKY_COLORS:
        return f"Tricky color space ({main_color}), rendering"

    return "Complex page layout, rendering"
