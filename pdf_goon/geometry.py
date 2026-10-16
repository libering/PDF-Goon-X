"""Geometry space model: page dimensions, image placed bounding boxes, bleed margins, and orientation."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


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
        import pypdfium2.raw as raw  # type: ignore[import-untyped]

        # 1. Effective Visual Box dimensions (CropBox if defined, falling back to MediaBox)
        page_w, page_h = 0.0, 0.0
        if hasattr(pdfium_page, "get_size"):
            page_w, page_h = pdfium_page.get_size()

        # 2. Page-level rotation (/Rotate entry: 0, 90, 180, 270)
        has_page_rotation = False
        if hasattr(pdfium_page, "get_rotation"):
            page_rotation = pdfium_page.get_rotation()
            has_page_rotation = (page_rotation % 360) != 0

        image_bboxes: list[tuple[float, float, float, float]] = []
        has_image_rotation = False

        if hasattr(pdfium_page, "get_objects"):
            for obj in pdfium_page.get_objects(filter=(raw.FPDF_PAGEOBJ_IMAGE,)):
                # Query placed bounding box in PDF points (xmin, ymin, xmax, ymax)
                bounds = obj.get_bounds()
                image_bboxes.append(bounds)

                # Check if image has rotation or shearing in its CTM
                if hasattr(obj, "get_matrix"):
                    try:
                        m = obj.get_matrix()
                        # In standard upright placement, b == 0 and c == 0
                        if abs(m.b) > 1e-3 or abs(m.c) > 1e-3:
                            has_image_rotation = True
                        # Mirrored / inverted placement
                        if m.a < -1e-3 or m.d < -1e-3:
                            has_image_rotation = True
                    except Exception:
                        pass

                # Check quadrilateral corner points
                if hasattr(obj, "get_quad_points"):
                    try:
                        quad = obj.get_quad_points()
                        if quad and len(quad) == 4:
                            p1, p2, _, _ = quad
                            dx = p2[0] - p1[0]
                            dy = p2[1] - p1[1]
                            # If bottom edge has significant vertical component, image is rotated
                            if abs(dy) > 1e-3 and abs(dx) > 1e-3:
                                has_image_rotation = True
                    except Exception:
                        pass

        has_rotation = has_page_rotation or has_image_rotation
        return (page_w, page_h), image_bboxes, has_rotation
    except Exception as e:
        logger.warning(f"Error extracting page geometry from pdfium: {e}")
        return (0.0, 0.0), [], False


def is_full_page_image(
    placed_bbox: tuple[float, float, float, float] | None,
    page_size: tuple[float, float],
    px_size: tuple[int, int],
    min_width: int,
    area_threshold: float = 0.95,
    max_margin_pts: float = 3.0,
) -> bool:
    """Determine whether an image substantially covers the entire page.

    Uses dual evaluation criteria:
    1. Absolute physical bleed margin tolerance: all 4 margins <= max_margin_pts.
    2. Relative area and dimension coverage:
       C_area >= area_threshold AND C_w >= 0.90 AND C_h >= 0.90.

    Requires px_w >= min_width.
    If placed_bbox is None, falls back to pixel aspect ratio coverage check.
    """
    page_w, page_h = page_size
    px_w, px_h = px_size

    if page_w <= 0.0 or page_h <= 0.0 or px_w < min_width:
        return False

    if placed_bbox is not None:
        xmin, ymin, xmax, ymax = placed_bbox
        w_placed = max(0.0, xmax - xmin)
        h_placed = max(0.0, ymax - ymin)

        if w_placed <= 0.0 or h_placed <= 0.0:
            return False

        # Criterion 1: Absolute physical bleed margin tolerance (with numerical epsilon)
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

        # Criterion 2: Relative area and dimension coverage
        c_w = w_placed / page_w
        c_h = h_placed / page_h
        c_area = (w_placed * h_placed) / (page_w * page_h)

        return (c_area >= area_threshold) and (c_w >= 0.90) and (c_h >= 0.90)

    # Fallback when placed_bbox is not available: pixel aspect ratio coverage
    width_dpi = (px_w * 72.0) / page_w
    height_dpi = (px_h * 72.0) / page_h

    if width_dpi > 0 and height_dpi > 0:
        coverage_normal = min(width_dpi, height_dpi) / max(width_dpi, height_dpi)
        if coverage_normal >= area_threshold:
            return True

    return False
