# tests.test_analyze_dpi — Property tests for DPI calculation and geometry heuristics

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.analyze import decide_processing_mode
from pdf_goon.models import (
    DPI_MAX,
    DPI_MIN,
    ImageInfo,
    PageInfo,
    ProcessingMode,
)


# Property 1: Candidate DPI Formula Correctness
@settings(max_examples=100)
@given(
    width_pts=st.floats(
        min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False
    ),
    height_pts=st.floats(
        min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False
    ),
    img_width=st.integers(min_value=100, max_value=50000),
    img_height=st.integers(min_value=100, max_value=50000),
    min_width=st.integers(min_value=1, max_value=99),
    dpi_text=st.integers(min_value=36, max_value=2400),
)
def test_prop1_candidate_dpi_formula(
    width_pts: float,
    height_pts: float,
    img_width: int,
    img_height: int,
    min_width: int,
    dpi_text: int,
) -> None:
    images = [
        ImageInfo(width=img_width, height=img_height, color="cmyk", is_mask=False)
    ]
    page_info = PageInfo(width_pts=width_pts, height_pts=height_pts)

    decision = decide_processing_mode(
        images, page_info, min_width, dpi_text, force_render=False
    )

    expected_width_dpi = (img_width * 72) / width_pts
    expected_height_dpi = (img_height * 72) / height_pts
    expected_candidate = max(expected_width_dpi, expected_height_dpi)
    expected_final = max(
        DPI_MIN, min(DPI_MAX, max(expected_candidate, float(dpi_text)))
    )

    assert abs(decision.dpi - expected_final) < 0.01


# Property 2: Filtering Gate and Max Selection
@settings(max_examples=100)
@given(
    img1_w=st.integers(min_value=1, max_value=99),
    img2_w=st.integers(min_value=100, max_value=5000),
    img3_w=st.integers(min_value=100, max_value=5000),
    page_w=st.floats(min_value=100.0, max_value=1000.0),
    page_h=st.floats(min_value=100.0, max_value=1000.0),
)
def test_prop2_filtering_gate_and_max_selection(
    img1_w: int, img2_w: int, img3_w: int, page_w: float, page_h: float
) -> None:
    images = [
        ImageInfo(width=img1_w, height=100, color="rgb", is_mask=False),
        ImageInfo(width=img2_w, height=100, color="rgb", is_mask=False),
        ImageInfo(width=img3_w, height=100, color="cmyk", is_mask=False),
    ]
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)

    decision = decide_processing_mode(
        images, page_info, min_width=100, dpi_text=72, force_render=False
    )

    cand2 = max((img2_w * 72) / page_w, (100 * 72) / page_h)
    cand3 = max((img3_w * 72) / page_w, (100 * 72) / page_h)
    expected_candidate = max(cand2, cand3)
    expected_final = max(DPI_MIN, min(DPI_MAX, max(expected_candidate, 72.0)))

    assert decision.mode is ProcessingMode.RENDER
    assert abs(decision.dpi - expected_final) < 0.01


# Property 3: Never-Downgrade Invariant
@settings(max_examples=100)
@given(
    images_w=st.lists(st.integers(min_value=1, max_value=5000), min_size=1, max_size=5),
    min_width=st.integers(min_value=50, max_value=100),
    dpi_text=st.integers(min_value=150, max_value=600),
)
def test_prop3_never_downgrade(
    images_w: list[int], min_width: int, dpi_text: int
) -> None:
    images = [
        ImageInfo(width=w, height=100, color="cmyk", is_mask=False) for w in images_w
    ]
    page_info = PageInfo(width_pts=500.0, height_pts=500.0)

    decision = decide_processing_mode(
        images, page_info, min_width, dpi_text, force_render=False
    )

    if any(w >= min_width for w in images_w):
        assert decision.dpi >= min(dpi_text, DPI_MAX)


# Property 4: Clamping Invariant
@settings(max_examples=100)
@given(
    img_w=st.integers(min_value=1, max_value=100000),
    img_h=st.integers(min_value=1, max_value=100000),
    page_w=st.floats(min_value=0.01, max_value=10000.0),
    page_h=st.floats(min_value=0.01, max_value=10000.0),
    dpi_text=st.integers(min_value=1, max_value=10000),
)
def test_prop4_clamping_invariant(
    img_w: int, img_h: int, page_w: float, page_h: float, dpi_text: int
) -> None:
    images = [ImageInfo(width=img_w, height=img_h, color="cmyk", is_mask=False)]
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)

    decision = decide_processing_mode(
        images, page_info, min_width=1, dpi_text=dpi_text, force_render=False
    )

    assert DPI_MIN <= decision.dpi <= DPI_MAX


# Property 5: Fallback When No Qualifying Images (but at least one image exists)
@settings(max_examples=100)
@given(
    images_w=st.lists(st.integers(min_value=1, max_value=99), min_size=1, max_size=5),
    dpi_text=st.integers(min_value=100, max_value=1000),
)
def test_prop5_fallback_no_qualifying_images(
    images_w: list[int], dpi_text: int
) -> None:
    images = [
        ImageInfo(width=w, height=100, color="rgb", is_mask=False) for w in images_w
    ]
    page_info = PageInfo(width_pts=500.0, height_pts=500.0)

    decision = decide_processing_mode(
        images, page_info, min_width=100, dpi_text=dpi_text, force_render=False
    )

    expected = max(DPI_MIN, min(DPI_MAX, float(dpi_text)))
    assert decision.mode is ProcessingMode.RENDER
    assert decision.dpi == expected


# Property 6: Non-Regression vs Old Formula
@settings(max_examples=100)
@given(
    img_w=st.integers(min_value=100, max_value=5000),
    img_h=st.integers(min_value=100, max_value=5000),
    page_w=st.floats(min_value=100.0, max_value=1000.0),
    page_h=st.floats(min_value=100.0, max_value=1000.0),
)
def test_prop6_non_regression_vs_old_formula(
    img_w: int, img_h: int, page_w: float, page_h: float
) -> None:
    images = [ImageInfo(width=img_w, height=img_h, color="cmyk", is_mask=False)]
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)

    decision = decide_processing_mode(
        images, page_info, min_width=50, dpi_text=72, force_render=False
    )

    old_formula_dpi = (img_w * 72) / page_w
    old_formula_dpi = max(DPI_MIN, min(DPI_MAX, max(old_formula_dpi, 72.0)))

    assert decision.dpi >= old_formula_dpi


# Property 7: Determinism
@settings(max_examples=100)
@given(
    img_w=st.integers(min_value=1, max_value=5000),
    page_w=st.floats(min_value=100.0, max_value=1000.0),
)
def test_prop7_determinism(img_w: int, page_w: float) -> None:
    images = [ImageInfo(width=img_w, height=100, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=page_w, height_pts=500.0)

    d1 = decide_processing_mode(
        images, page_info, min_width=50, dpi_text=72, force_render=False
    )
    d2 = decide_processing_mode(
        images, page_info, min_width=50, dpi_text=72, force_render=False
    )

    assert d1 == d2


# Property 8: Single image that fills page → EXTRACT; doesn't fill → RENDER
@settings(max_examples=100)
@given(
    dpi=st.floats(
        min_value=36.0, max_value=1200.0, allow_nan=False, allow_infinity=False
    ),
    page_w=st.floats(min_value=100.0, max_value=1000.0),
    page_h=st.floats(min_value=100.0, max_value=1000.0),
)
def test_prop8_single_extractable_image(
    dpi: float, page_w: float, page_h: float
) -> None:
    """A single image with matching page aspect ratio (full coverage) extracts."""
    # Image sized to fill the entire page at the given DPI
    img_w = int(page_w * dpi / 72)
    img_h = int(page_h * dpi / 72)

    # Ensure image is wider than min_width (which we set low)
    if img_w < 150:
        return  # Skip: image too small for this test

    images = [ImageInfo(width=img_w, height=img_h, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)

    decision = decide_processing_mode(
        images, page_info, min_width=100, dpi_text=72, force_render=False
    )

    # Full-page image should extract
    assert decision.mode is ProcessingMode.EXTRACT
    assert decision.dpi == 0


@settings(max_examples=100)
@given(
    img_w=st.integers(min_value=101, max_value=5000),
    img_h=st.integers(min_value=50, max_value=500),
)
def test_prop8b_single_image_not_filling_page_renders(img_w: int, img_h: int) -> None:
    """A single image that doesn't fill the page renders to preserve background."""
    # Square page, but image has different aspect ratio (won't fill page)
    page_info = PageInfo(width_pts=500.0, height_pts=500.0)
    images = [ImageInfo(width=img_w, height=img_h, color="rgb", is_mask=False)]

    # Skip if by chance the image has matching aspect ratio (fills page)
    width_dpi = img_w * 72 / 500.0
    height_dpi = img_h * 72 / 500.0
    if width_dpi <= 0 or height_dpi <= 0:
        return
    coverage = min(width_dpi, height_dpi) / max(width_dpi, height_dpi)
    if coverage >= 0.95:
        return  # Image fills page, skip this test case

    decision = decide_processing_mode(
        images, page_info, min_width=100, dpi_text=72, force_render=False
    )

    # Image doesn't fill page → should render
    assert decision.mode is ProcessingMode.RENDER
    assert decision.dpi > 0


