"""PDF inspection: page count, image metadata, page dimensions, and processing decisions."""

from __future__ import annotations

import logging
import struct
from pathlib import Path

from pdf_goon.models import (
    DPI_MAX,
    DPI_MIN,
    TRICKY_COLORS,
    ImageInfo,
    PageDecision,
    PageInfo,
    ProcessingMode,
)

logger = logging.getLogger(__name__)


def get_page_count(pdf_path: Path) -> int | None:
    """Return total page count, or None if PDF is unreadable."""
    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            return len(reader.pages)
    except Exception:
        return None


def get_image_data(
    pdf_path: Path,
    page_num: int,
) -> tuple[list[ImageInfo], list[str], bool]:
    """Return (images, mask_indices, has_text) for a given page.

    has_text is True when the page defines Font resources, indicating
    text content that would be lost by a raw image extraction.
    """
    images: list[ImageInfo] = []
    mask_indices: list[str] = []
    has_text = False

    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page = reader.pages[page_num - 1]

            # Detect text: if the page has /Font resources it contains text operators
            resources = page.get("/Resources")
            if resources and "/Font" in resources:
                has_text = True

            for img_idx, img_file in enumerate(page.images):
                pil_image = img_file.image
                if pil_image is None:
                    width = 0
                    height = 0
                    color = "unknown"
                else:
                    try:
                        width = pil_image.width
                        height = pil_image.height
                        color = pil_image.mode.lower()
                    except Exception:
                        width = 0
                        height = 0
                        color = "unknown"

                # In pypdf, masks are often 1-bit mode ('1'). We use this as a heuristic
                # since pypdf abstracts away the /ImageMask dictionary field.
                is_mask = color == "1"
                if is_mask:
                    mask_indices.append(str(img_idx).zfill(3))
                else:
                    images.append(
                        ImageInfo(
                            width=width,
                            height=height,
                            color=color,
                            is_mask=False,
                        )
                    )
    except Exception as e:
        logger.warning(f"Error parsing images with pypdf: {e}")

    return images, mask_indices, has_text


def get_page_info(
    pdf_path: Path,
    page_num: int,
) -> PageInfo:
    """Return physical page dimensions in points."""
    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page = reader.pages[page_num - 1]
            box = page.mediabox
            return PageInfo(width_pts=float(box.width), height_pts=float(box.height))
    except Exception:
        return PageInfo(width_pts=0.0, height_pts=0.0)


# Coverage threshold: image must cover at least this fraction of page in both dimensions
EXTRACT_COVERAGE_THRESHOLD = 0.95


def _image_fills_page(main_img: ImageInfo, page_info: PageInfo) -> bool:
    """Check if a single image truly fills the page in both dimensions.

    Returns True only if the image covers at least EXTRACT_COVERAGE_THRESHOLD
    of the page in both width and height dimensions. Also checks rotated orientation.
    """
    if page_info.width_pts <= 0 or page_info.height_pts <= 0:
        return False

    # Calculate DPI if image filled page width/height
    width_dpi = (main_img.width * 72) / page_info.width_pts
    height_dpi = (main_img.height * 72) / page_info.height_pts

    # Check normal orientation
    if width_dpi > 0 and height_dpi > 0:
        coverage_normal = min(width_dpi, height_dpi) / max(width_dpi, height_dpi)
        if coverage_normal >= EXTRACT_COVERAGE_THRESHOLD:
            return True

    # Check rotated orientation (image rotated 90° relative to page)
    width_dpi_rot = (main_img.width * 72) / page_info.height_pts
    height_dpi_rot = (main_img.height * 72) / page_info.width_pts

    if width_dpi_rot > 0 and height_dpi_rot > 0:
        coverage_rot = min(width_dpi_rot, height_dpi_rot) / max(
            width_dpi_rot, height_dpi_rot
        )
        if coverage_rot >= EXTRACT_COVERAGE_THRESHOLD:
            # Image fills page but rotated - don't extract (would lose rotation)
            return False

    return False


def decide_processing_mode(
    images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
    force_render: bool,
    *,
    has_text: bool = False,
    keep_blank: bool = False,
) -> PageDecision:
    """Determine whether to extract, render, or skip (blank)."""
    if force_render:
        dpi = _clamp_dpi(float(dpi_text))
        return PageDecision(
            mode=ProcessingMode.RENDER, dpi=dpi, reason="Force render enabled"
        )

    non_mask_images = [img for img in images if not img.is_mask]
    is_tricky = any(img.color in TRICKY_COLORS for img in non_mask_images)

    # BLANK detection: no images AND no text — skip early to avoid wasted computation
    if not non_mask_images and not has_text:
        if keep_blank:
            dpi = _clamp_dpi(float(dpi_text))
            return PageDecision(
                mode=ProcessingMode.RENDER,
                dpi=dpi,
                reason="Blank page, rendering due to --keep-blank",
            )
        return PageDecision(
            mode=ProcessingMode.BLANK,
            dpi=0,
            reason="Blank page (no images, no text)",
        )

    # Single non-mask image, not tricky color, wider than min_width, NO text → extract
    if len(non_mask_images) == 1 and not is_tricky and not has_text:
        main_img = non_mask_images[0]
        if main_img.width > min_width:
            # Check if image truly fills the page (high coverage in both dimensions)
            # Only extract if image truly fills the page to avoid white margins
            if _image_fills_page(main_img, page_info):
                return PageDecision(
                    mode=ProcessingMode.EXTRACT,
                    dpi=0,
                    reason="Single extractable image filling page",
                )
            # Image doesn't fill page -> render to preserve background/margins
            reason = (
                "Single image but doesn't fill page, rendering to preserve background"
            )
            dpi = _compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
            return PageDecision(mode=ProcessingMode.RENDER, dpi=dpi, reason=reason)

    # Otherwise → render
    dpi = _compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
    reason = _build_render_reason(non_mask_images, min_width, dpi_text, has_text)
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

    qualifying_images = [img for img in images if img.width >= min_width]
    if not qualifying_images:
        return _clamp_dpi(float(dpi_text))

    candidates = []
    for img in qualifying_images:
        width_dpi = (
            (img.width * 72) / page_info.width_pts
            if page_info.width_pts > 0
            else float(dpi_text)
        )
        height_dpi = (
            (img.height * 72) / page_info.height_pts
            if page_info.height_pts > 0
            else float(dpi_text)
        )
        candidate_dpi = max(width_dpi, height_dpi)
        logger.debug(
            f"Image {img.width}x{img.height}: width_dpi={width_dpi:.2f}, height_dpi={height_dpi:.2f} -> candidate={candidate_dpi:.2f}"
        )
        candidates.append(candidate_dpi)

    max_candidate = max(candidates)
    final_dpi = max(max_candidate, float(dpi_text))
    logger.debug(f"Selected render DPI: {final_dpi:.2f}")

    return _clamp_dpi(final_dpi)


def _build_render_reason(
    images: list[ImageInfo], min_width: int, dpi_text: int, has_text: bool = False
) -> str:
    """Build a human-readable reason string for render mode."""
    if not images:
        return f"No images, using fallback DPI {dpi_text}"

    largest_width = max(img.width for img in images)

    if has_text and len(images) == 1 and largest_width >= min_width:
        return "Text + image page, rendering to preserve layout"

    if largest_width < min_width:
        return f"Small images (max {largest_width}px < {min_width}px), using fallback DPI {dpi_text}"

    if len(images) > 1:
        return f"Multiple images ({len(images)}), rendering at computed DPI"

    # Tricky color or other reason
    main_color = images[0].color if images else "unknown"
    if main_color in TRICKY_COLORS:
        return f"Tricky color space ({main_color}), rendering"

    return "Complex page layout, rendering"
