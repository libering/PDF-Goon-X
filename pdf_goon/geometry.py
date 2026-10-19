"""Geometry space model: page dimensions, image placed bounding boxes, bleed margins, and orientation."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _extract_page_dim_and_rot(pdfium_page: object) -> tuple[float, float, bool]:
    """Extract page visual dimensions and /Rotate status."""
    page_w, page_h = 0.0, 0.0
    if hasattr(pdfium_page, "get_size"):
        page_w, page_h = pdfium_page.get_size()

    has_page_rotation = False
    if hasattr(pdfium_page, "get_rotation"):
        page_rotation = pdfium_page.get_rotation()
        has_page_rotation = (page_rotation % 360) != 0

    return page_w, page_h, has_page_rotation


def _inspect_obj_rotation(obj: object) -> bool:
    """Check if image object has rotation or shearing in CTM matrix or quad points."""
    if hasattr(obj, "get_matrix"):
        try:
            m = obj.get_matrix()
            if abs(m.b) > 1e-3 or abs(m.c) > 1e-3 or m.a < -1e-3 or m.d < -1e-3:
                return True
        except Exception:
            pass

    if hasattr(obj, "get_quad_points"):
        try:
            quad = obj.get_quad_points()
            if quad and len(quad) == 4:
                p1, p2, _, _ = quad
                if abs(p2[1] - p1[1]) > 1e-3 and abs(p2[0] - p1[0]) > 1e-3:
                    return True
        except Exception:
            pass

    return False


def _extract_image_objects(
    pdfium_page: object,
) -> tuple[list[tuple[float, float, float, float]], bool]:
    """Extract bounding boxes and rotation flags from page image objects."""
    import pypdfium2.raw as raw

    image_bboxes: list[tuple[float, float, float, float]] = []
    has_image_rotation = False

    if hasattr(pdfium_page, "get_objects"):
        for obj in pdfium_page.get_objects(filter=(raw.FPDF_PAGEOBJ_IMAGE,)):
            image_bboxes.append(obj.get_bounds())
            if _inspect_obj_rotation(obj):
                has_image_rotation = True

    return image_bboxes, has_image_rotation


def extract_page_geometry(
    pdfium_page: object,
) -> tuple[tuple[float, float], list[tuple[float, float, float, float]], bool]:
    """Extract page visual dimensions, image placed bounding boxes, and rotation state.

    Args:
        pdfium_page: A pypdfium2.PdfPage object.

    Returns:
        ((page_w, page_h), [bbox_1, bbox_2, ...], has_rotation)
        where each bbox is (xmin, ymin, xmax, ymax) in PDF points.
    """
    if pdfium_page is None:
        return (0.0, 0.0), [], False

    try:
        page_w, page_h, has_page_rotation = _extract_page_dim_and_rot(pdfium_page)
        image_bboxes, has_image_rotation = _extract_image_objects(pdfium_page)
        has_rotation = has_page_rotation or has_image_rotation
        return (page_w, page_h), image_bboxes, has_rotation
    except Exception as e:
        logger.warning(f"Error extracting page geometry from pdfium: {e}")
        return (0.0, 0.0), [], False


def _check_placed_bbox_coverage(
    placed_bbox: tuple[float, float, float, float],
    page_w: float,
    page_h: float,
    area_threshold: float,
    max_margin_pts: float,
) -> bool:
    """Evaluate absolute bleed margin and relative area coverage."""
    xmin, ymin, xmax, ymax = placed_bbox
    w_placed = max(0.0, xmax - xmin)
    h_placed = max(0.0, ymax - ymin)

    if w_placed <= 0.0 or h_placed <= 0.0:
        return False

    eps = 1e-6
    margin_l = max(0.0, xmin)
    margin_r = max(0.0, page_w - xmax)
    margin_b = max(0.0, ymin)
    margin_t = max(0.0, page_h - ymax)

    if (
        margin_l <= max_margin_pts + eps
        and margin_r <= max_margin_pts + eps
        and margin_b <= max_margin_pts + eps
        and margin_t <= max_margin_pts + eps
    ):
        return True

    c_w = w_placed / page_w
    c_h = h_placed / page_h
    c_area = (w_placed * h_placed) / (page_w * page_h)
    return (c_area >= area_threshold) and (c_w >= 0.90) and (c_h >= 0.90)


def _check_pixel_ratio_coverage(
    px_w: int,
    px_h: int,
    page_w: float,
    page_h: float,
    area_threshold: float,
) -> bool:
    """Fallback aspect ratio coverage check when placed_bbox is unavailable."""
    width_dpi = (px_w * 72.0) / page_w
    height_dpi = (px_h * 72.0) / page_h

    if width_dpi > 0 and height_dpi > 0:
        coverage_normal = min(width_dpi, height_dpi) / max(width_dpi, height_dpi)
        return coverage_normal >= area_threshold

    return False


def is_full_page_image(
    placed_bbox: tuple[float, float, float, float] | None,
    page_size: tuple[float, float],
    px_size: tuple[int, int],
    min_width: int,
    area_threshold: float = 0.95,
    max_margin_pts: float = 3.0,
) -> bool:
    """Determine whether an image substantially covers the entire page."""
    page_w, page_h = page_size
    px_w, px_h = px_size

    if page_w <= 0.0 or page_h <= 0.0 or px_w < min_width:
        return False

    if placed_bbox is not None:
        return _check_placed_bbox_coverage(
            placed_bbox, page_w, page_h, area_threshold, max_margin_pts
        )

    return _check_pixel_ratio_coverage(px_w, px_h, page_w, page_h, area_threshold)
