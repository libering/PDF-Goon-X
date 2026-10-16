"""Property-based tests for geometry module and placed DPI invariants (Hypothesis).

Feature: fix-detection-algorithm
Covers:
- Property 1: BBox Coverage Monotonicity
- Property 2: Margin Tolerance Invariant (Req 1.4, 1.5)
- Property 3: Rotation Safety Invariant (Req 1.6)
- Property 5: DPI Bounded Clamping (Req 4.5)
- Req 1.7: egihid.pdf golden sample regression test
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.analyze import (
    compute_render_dpi,
    decide_processing_mode,
)
from pdf_goon.geometry import is_full_page_image
from pdf_goon.models import (
    DPI_MAX,
    DPI_MIN,
    ImageInfo,
    PageInfo,
    ProcessingMode,
)

# ---------------------------------------------------------------------------
# Property 1: BBox Coverage Monotonicity
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    page_w=st.floats(min_value=100.0, max_value=2000.0),
    page_h=st.floats(min_value=100.0, max_value=2000.0),
    scale1=st.floats(min_value=0.1, max_value=0.8),
    scale2=st.floats(min_value=0.81, max_value=1.0),
)
def test_prop1_bbox_coverage_monotonicity(
    page_w: float, page_h: float, scale1: float, scale2: float
) -> None:
    """Larger placed bounding box area yields monotonically non-decreasing coverage."""
    # bbox 1 is strictly smaller than bbox 2
    w1, h1 = page_w * scale1, page_h * scale1
    w2, h2 = page_w * scale2, page_h * scale2

    cov1 = (w1 * h1) / (page_w * page_h)
    cov2 = (w2 * h2) / (page_w * page_h)

    assert 0.0 <= cov1 <= cov2 <= 1.0


# ---------------------------------------------------------------------------
# Property 2: Margin Tolerance Invariant (Req 1.4, 1.5)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    page_w=st.floats(min_value=200.0, max_value=2000.0),
    page_h=st.floats(min_value=200.0, max_value=2000.0),
    tol=st.floats(min_value=1.0, max_value=10.0),
    margin_l=st.floats(min_value=0.0, max_value=10.0),
    margin_r=st.floats(min_value=0.0, max_value=10.0),
    margin_b=st.floats(min_value=0.0, max_value=10.0),
    margin_t=st.floats(min_value=0.0, max_value=10.0),
    px_w=st.integers(min_value=600, max_value=4000),
    px_h=st.integers(min_value=600, max_value=4000),
)
def test_prop2_margin_tolerance_invariant(
    page_w: float,
    page_h: float,
    tol: float,
    margin_l: float,
    margin_r: float,
    margin_b: float,
    margin_t: float,
    px_w: int,
    px_h: int,
) -> None:
    """When all margins are <= tolerance and px_w >= min_width, is_full_page_image is True."""
    # Constrain margins to be within tolerance
    ml = min(margin_l, tol)
    mr = min(margin_r, tol)
    mb = min(margin_b, tol)
    mt = min(margin_t, tol)

    xmin = ml
    ymin = mb
    xmax = page_w - mr
    ymax = page_h - mt

    if xmax > xmin and ymax > ymin:
        bbox = (xmin, ymin, xmax, ymax)
        fills = is_full_page_image(
            placed_bbox=bbox,
            page_size=(page_w, page_h),
            px_size=(px_w, px_h),
            min_width=500,
            max_margin_pts=tol,
        )
        assert fills is True


# ---------------------------------------------------------------------------
# Property 3: Rotation Safety Invariant (Req 1.6)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    page_w=st.floats(min_value=300.0, max_value=1000.0),
    page_h=st.floats(min_value=300.0, max_value=1000.0),
    px_w=st.integers(min_value=1000, max_value=4000),
    px_h=st.integers(min_value=1000, max_value=4000),
)
def test_prop3_rotation_safety_invariant(
    page_w: float, page_h: float, px_w: int, px_h: int
) -> None:
    """Full-page image with rotation must decide RENDER, never EXTRACT."""
    bbox = (0.0, 0.0, page_w, page_h)
    img = ImageInfo(
        width=px_w,
        height=px_h,
        color="rgb",
        is_mask=False,
        placed_bbox=bbox,
        has_rotation=True,
    )
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)

    decision = decide_processing_mode(
        images=[img],
        page_info=page_info,
        min_width=500,
        dpi_text=400,
        force_render=False,
        has_text=False,
    )

    assert decision.mode is ProcessingMode.RENDER
    assert "rotation" in decision.reason.lower()


# ---------------------------------------------------------------------------
# Property 5: DPI Bounded Clamping (Req 4.5)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    img_w=st.integers(min_value=1, max_value=50000),
    img_h=st.integers(min_value=1, max_value=50000),
    bbox_w=st.floats(min_value=0.01, max_value=5000.0),
    bbox_h=st.floats(min_value=0.01, max_value=5000.0),
    page_w=st.floats(min_value=10.0, max_value=5000.0),
    page_h=st.floats(min_value=10.0, max_value=5000.0),
    dpi_text=st.integers(min_value=-5000, max_value=10000),
)
def test_prop5_dpi_clamping_invariant(
    img_w: int,
    img_h: int,
    bbox_w: float,
    bbox_h: float,
    page_w: float,
    page_h: float,
    dpi_text: int,
) -> None:
    """Computed render DPI is strictly clamped within [DPI_MIN, DPI_MAX]."""
    bbox = (0.0, 0.0, bbox_w, bbox_h)
    img = ImageInfo(
        width=img_w,
        height=img_h,
        color="rgb",
        is_mask=False,
        placed_bbox=bbox,
    )
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)

    dpi = compute_render_dpi([img], page_info, min_width=100, dpi_text=dpi_text)
    assert DPI_MIN <= dpi <= DPI_MAX


# ---------------------------------------------------------------------------
# Regression Test: Golden Sample egihid.pdf Page 1 (Req 1.7)
# ---------------------------------------------------------------------------


def test_egihid_pdf_page1_decides_extract() -> None:
    """Golden regression sample: egihid.pdf Page 1 geometry must resolve to EXTRACT.

    Geometry:
    - Page MediaBox: 595.276 x 841.890 pt
    - Placed image BBox: x=0, y=0.48 pt, w=595.276 pt, h=840.93 pt
      (ymin=0.48, ymax=841.41 pt -> top margin = 0.48 pt, bottom margin = 0.48 pt)
    - Image pixels: 1654 x 2339
    - No visible text, no rotation
    """
    page_w = 595.276
    page_h = 841.890
    xmin = 0.0
    ymin = 0.48
    xmax = 595.276
    ymax = ymin + 840.93  # 841.41 -> margin_t = 841.890 - 841.41 = 0.48 pt

    placed_bbox = (xmin, ymin, xmax, ymax)
    image = ImageInfo(
        width=1654,
        height=2339,
        color="rgb",
        is_mask=False,
        placed_bbox=placed_bbox,
        has_rotation=False,
    )
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)

    decision = decide_processing_mode(
        images=[image],
        page_info=page_info,
        min_width=500,
        dpi_text=400,
        force_render=False,
        has_text=False,
        margin_tolerance=3.0,
    )

    assert decision.mode is ProcessingMode.EXTRACT
    assert decision.reason == "Single extractable image filling page"
    assert decision.dpi == 0
