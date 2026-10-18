"""Processing mode decisions and DPI calculation for PDF pages."""

from __future__ import annotations

import logging

from pdf_goon.geometry import is_full_page_image
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

# Coverage threshold: image must cover at least this fraction of page in both dimensions
EXTRACT_COVERAGE_THRESHOLD = 0.95


def _clamp_dpi(dpi: float) -> float:
    """Clamp DPI to [DPI_MIN, DPI_MAX]."""
    return max(DPI_MIN, min(DPI_MAX, dpi))


def _calc_image_dpi(
    img: ImageInfo, page_info: PageInfo, dpi_text: int
) -> float:
    """Calculate candidate DPI for a single image placed on the page."""
    if img.placed_bbox is not None:
        xmin, ymin, xmax, ymax = img.placed_bbox
        w_placed = max(1.0, xmax - xmin)
        h_placed = max(1.0, ymax - ymin)
        width_dpi = (img.width * 72.0) / w_placed
        height_dpi = (img.height * 72.0) / h_placed
    else:
        width_dpi = (
            (img.width * 72.0) / page_info.width_pts
            if page_info.width_pts > 0
            else float(dpi_text)
        )
        height_dpi = (
            (img.height * 72.0) / page_info.height_pts
            if page_info.height_pts > 0
            else float(dpi_text)
        )
    candidate_dpi = max(width_dpi, height_dpi)
    logger.debug(
        f"Image {img.width}x{img.height}: width_dpi={width_dpi:.2f}, "
        f"height_dpi={height_dpi:.2f} -> candidate={candidate_dpi:.2f}"
    )
    return candidate_dpi


def compute_render_dpi(
    images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
) -> float:
    """Calculate the best rendering DPI based on embedded image placed dimensions."""
    if not images:
        return _clamp_dpi(float(dpi_text))

    qualifying_images = [
        img for img in images if not (img.width < min_width and img.height < min_width)
    ]
    if not qualifying_images:
        return _clamp_dpi(float(dpi_text))

    candidates = [
        _calc_image_dpi(img, page_info, dpi_text) for img in qualifying_images
    ]
    max_candidate = max(candidates)
    final_dpi = max(max_candidate, float(dpi_text))
    logger.debug(f"Selected render DPI: {final_dpi:.2f}")

    return _clamp_dpi(final_dpi)


# Alias for backwards compatibility
_compute_render_dpi = compute_render_dpi


def _image_fills_page(
    main_img: ImageInfo,
    page_info: PageInfo,
    min_width: int = 500,
    margin_tolerance: float = 3.0,
) -> bool:
    """Check if a single image truly fills the page using geometry or aspect ratio."""
    return is_full_page_image(
        placed_bbox=main_img.placed_bbox,
        page_size=(page_info.width_pts, page_info.height_pts),
        px_size=(main_img.width, main_img.height),
        min_width=min_width,
        area_threshold=EXTRACT_COVERAGE_THRESHOLD,
        max_margin_pts=margin_tolerance,
    )


def _build_render_reason(
    images: list[ImageInfo], min_width: int, dpi_text: int, has_text: bool = False
) -> str:
    """Build a human-readable reason string for render mode."""
    if not images:
        if has_text:
            return f"Text-only page, rendering at fallback DPI {dpi_text}"
        return f"No images, using fallback DPI {dpi_text}"

    largest_width = max(img.width for img in images)

    if has_text and len(images) == 1 and largest_width >= min_width:
        return "Text + image page, rendering to preserve layout"

    if largest_width < min_width:
        return f"Small images (max {largest_width}px < {min_width}px), using fallback DPI {dpi_text}"

    if len(images) > 1:
        return f"Multiple images ({len(images)}), rendering at computed DPI"

    main_color = images[0].color if images else "unknown"
    if main_color in TRICKY_COLORS:
        return f"Tricky color space ({main_color}), rendering"

    return "Complex page layout, rendering"


def _check_force_render(
    force_render: bool, dpi_text: int
) -> PageDecision | None:
    """Rule 1: Force render mode."""
    if force_render:
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=_clamp_dpi(float(dpi_text)),
            reason="Force render enabled",
        )
    return None


def _check_blank_or_mask_page(
    images: list[ImageInfo],
    non_mask_images: list[ImageInfo],
    has_text: bool,
    keep_blank: bool,
    dpi_text: int,
) -> PageDecision | None:
    """Rule 2: Mask-only, blank, or text-only pages without non-mask images."""
    if not non_mask_images and images and not has_text:
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=_clamp_dpi(float(dpi_text)),
            reason="Page contains only mask images, rendering to preserve visual content",
        )

    if not images and not has_text:
        if keep_blank:
            return PageDecision(
                mode=ProcessingMode.RENDER,
                dpi=_clamp_dpi(float(dpi_text)),
                reason="Blank page, rendering due to --keep-blank",
            )
        return PageDecision(
            mode=ProcessingMode.BLANK,
            dpi=0,
            reason="Blank page (no images, no text)",
        )

    if not non_mask_images and has_text:
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=_clamp_dpi(float(dpi_text)),
            reason=f"Text-only page, rendering at fallback DPI {dpi_text}",
        )

    return None


def _check_text_and_colors(
    non_mask_images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
    has_text: bool,
) -> PageDecision | None:
    """Rule 3: Tricky colors, mixed text-images, or small-images-only."""
    tricky_img = next(
        (img for img in non_mask_images if img.color in TRICKY_COLORS), None
    )
    if tricky_img is not None:
        dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason=f"Tricky color space ({tricky_img.color}), rendering",
        )

    if has_text and non_mask_images:
        dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason="Text + image page, rendering to preserve layout",
        )

    largest_width = max(img.width for img in non_mask_images)
    if largest_width < min_width:
        dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason=f"Small images (max {largest_width}px < {min_width}px), using fallback DPI {dpi_text}",
        )

    return None


def _check_image_geometry_and_counts(
    non_mask_images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
    margin_tolerance: float,
) -> PageDecision:
    """Rule 4: Multi-image layout or single image extraction geometry."""
    if len(non_mask_images) > 1:
        dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason=f"Multiple images ({len(non_mask_images)}), rendering at computed DPI",
        )

    main_img = non_mask_images[0]
    fills_page = _image_fills_page(
        main_img,
        page_info,
        min_width=min_width,
        margin_tolerance=margin_tolerance,
    )

    if fills_page:
        if main_img.has_rotation:
            dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
            return PageDecision(
                mode=ProcessingMode.RENDER,
                dpi=dpi,
                reason="Image fills page but has rotation, rendering to preserve orientation",
            )
        return PageDecision(
            mode=ProcessingMode.EXTRACT,
            dpi=0,
            reason="Single extractable image filling page",
        )

    dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
    return PageDecision(
        mode=ProcessingMode.RENDER,
        dpi=dpi,
        reason="Single image does not fill page, rendering to preserve background",
    )


def decide_processing_mode(
    images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
    force_render: bool,
    *,
    has_text: bool = False,
    keep_blank: bool = False,
    margin_tolerance: float = 3.0,
) -> PageDecision:
    """Determine whether to extract, render, or skip (blank)."""
    decision = _check_force_render(force_render, dpi_text)
    if decision is not None:
        return decision

    non_mask_images = [img for img in images if not img.is_mask]

    decision = _check_blank_or_mask_page(
        images, non_mask_images, has_text, keep_blank, dpi_text
    )
    if decision is not None:
        return decision

    decision = _check_text_and_colors(
        non_mask_images, page_info, min_width, dpi_text, has_text
    )
    if decision is not None:
        return decision

    return _check_image_geometry_and_counts(
        non_mask_images, page_info, min_width, dpi_text, margin_tolerance
    )
