# tests.test_analyze — Tests for pdf_goon.analyze

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.analyze import (
    _build_render_reason,
    decide_processing_mode,
    get_image_data,
    get_page_count,
    get_page_info,
)
from pdf_goon.models import (
    DPI_MAX,
    DPI_MIN,
    ImageInfo,
    PageInfo,
    ProcessingMode,
)


# --- Property Tests for improve-detection-quality ---


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


# --- Unit tests for get_page_count ---


DUMMY_PDF = Path("/tmp/test.pdf")
_mock_file = MagicMock()  # Reusable mock file object for open()


def test_get_page_count_returns_correct_count() -> None:
    """get_page_count extracts page count using pypdf."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_reader.return_value.pages = [1, 2, 3, 4, 5]
        result = get_page_count(DUMMY_PDF)
        assert result == 5


def test_get_page_count_returns_none_on_error() -> None:
    """get_page_count returns None when pypdf raises Exception."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader", side_effect=Exception("bad pdf")),
    ):
        result = get_page_count(DUMMY_PDF)
        assert result is None


# --- Unit tests for get_image_data ---


def test_get_image_data_parses_normal_images() -> None:
    """get_image_data correctly parses image entries using pypdf."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_img = MagicMock()
        mock_img.image.width = 1200
        mock_img.image.height = 800
        mock_img.image.mode = "RGB"

        mock_page = MagicMock()
        mock_page.images = [mock_img]
        mock_page.get.return_value = {}
        mock_reader.return_value.pages = [mock_page]

        images, masks, has_text = get_image_data(DUMMY_PDF, 1)

        assert len(images) == 1
        assert images[0].width == 1200
        assert images[0].height == 800
        assert images[0].color == "rgb"
        assert images[0].is_mask is False
        assert has_text is False


def test_get_image_data_identifies_mask() -> None:
    """get_image_data identifies masks using 1-bit heuristic."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_img1 = MagicMock()
        mock_img1.image.mode = "RGB"
        mock_img2 = MagicMock()
        mock_img2.image.mode = "1"  # Mask

        mock_page = MagicMock()
        mock_page.images = [mock_img1, mock_img2]
        mock_page.get.return_value = {}
        mock_reader.return_value.pages = [mock_page]

        images, masks, has_text = get_image_data(DUMMY_PDF, 1)

        assert len(masks) == 1
        assert masks[0] == "001"


def test_get_image_data_detects_text() -> None:
    """get_image_data detects text via /Font resources."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_page = MagicMock()
        mock_page.images = []
        mock_page.get.return_value = {"/Font": {"/F1": {}}}
        mock_reader.return_value.pages = [mock_page]

        _, _, has_text = get_image_data(DUMMY_PDF, 1)
        assert has_text is True


def test_get_image_data_returns_empty_on_error() -> None:
    """get_image_data returns empty lists when pypdf fails."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader", side_effect=Exception("error")),
    ):
        images, masks, has_text = get_image_data(DUMMY_PDF, 1)

        assert images == []
        assert masks == []
        assert has_text is False


# --- Unit tests for get_page_info ---


def test_get_page_info_parses_dimensions() -> None:
    """get_page_info parses page dimensions using pypdf mediabox."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_page = MagicMock()
        mock_page.mediabox.width = 612.0
        mock_page.mediabox.height = 792.0
        mock_reader.return_value.pages = [mock_page]

        info = get_page_info(DUMMY_PDF, 1)

        assert abs(info.width_pts - 612.0) < 0.01
        assert abs(info.height_pts - 792.0) < 0.01


def test_get_page_info_returns_zero_on_failure() -> None:
    """get_page_info returns (0.0, 0.0) when pypdf fails."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader", side_effect=Exception("error")),
    ):
        info = get_page_info(DUMMY_PDF, 1)

        assert info.width_pts == 0.0
        assert info.height_pts == 0.0


# --- Unit tests for decide_processing_mode ---


def test_decide_single_large_image_extracts() -> None:
    """Single large image wider than min_width, NO text, triggers EXTRACT mode.

    Image must truly fill the page (high coverage in both dimensions) to extract.
    """
    # Full-page image at ~200 DPI on 612x792 pt page (letter size)
    images = [ImageInfo(width=1700, height=2200, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(
        images, page_info, min_width=500, dpi_text=400, force_render=False
    )

    assert decision.mode is ProcessingMode.EXTRACT
    assert decision.dpi == 0


def test_decide_single_large_image_with_text_renders() -> None:
    """Single large image WITH text triggers RENDER mode to preserve text."""
    images = [ImageInfo(width=1200, height=800, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(
        images,
        page_info,
        min_width=500,
        dpi_text=400,
        force_render=False,
        has_text=True,
    )

    assert decision.mode is ProcessingMode.RENDER
    assert DPI_MIN <= decision.dpi <= DPI_MAX


def test_decide_multiple_images_renders() -> None:
    """Multiple non-mask images trigger RENDER mode."""
    images = [
        ImageInfo(width=1200, height=800, color="rgb", is_mask=False),
        ImageInfo(width=600, height=400, color="rgb", is_mask=False),
    ]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(
        images, page_info, min_width=500, dpi_text=400, force_render=False
    )

    assert decision.mode is ProcessingMode.RENDER
    assert DPI_MIN <= decision.dpi <= DPI_MAX


def test_decide_force_render_overrides() -> None:
    """force_render=True always triggers RENDER mode regardless of image count."""
    images = [ImageInfo(width=1200, height=800, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(
        images, page_info, min_width=500, dpi_text=400, force_render=True
    )

    assert decision.mode is ProcessingMode.RENDER
    assert DPI_MIN <= decision.dpi <= DPI_MAX


def test_decide_small_image_icon_renders_at_dpi_text() -> None:
    """Single small image (icon) narrower than min_width triggers RENDER at dpi_text."""
    images = [ImageInfo(width=100, height=100, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(
        images, page_info, min_width=500, dpi_text=400, force_render=False
    )

    assert decision.mode is ProcessingMode.RENDER
    assert decision.dpi == 400.0


def test_decide_tricky_color_renders() -> None:
    """Single image with tricky color (cmyk) triggers RENDER mode."""
    images = [ImageInfo(width=1200, height=800, color="cmyk", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(
        images, page_info, min_width=500, dpi_text=400, force_render=False
    )

    assert decision.mode is ProcessingMode.RENDER
    assert DPI_MIN <= decision.dpi <= DPI_MAX


# --- Unit Tests for Reason Strings and Logging ---


def test_reason_string_no_images() -> None:
    reason = _build_render_reason([], 500, 400)
    assert reason == "No images, using fallback DPI 400"


def test_reason_string_small_images() -> None:
    images = [ImageInfo(width=100, height=100, color="rgb", is_mask=False)]
    reason = _build_render_reason(images, 500, 400)
    assert reason == "Small images (max 100px < 500px), using fallback DPI 400"


def test_reason_string_multiple_images() -> None:
    images = [
        ImageInfo(width=600, height=100, color="rgb", is_mask=False),
        ImageInfo(width=600, height=100, color="rgb", is_mask=False),
    ]
    reason = _build_render_reason(images, 500, 400)
    assert reason == "Multiple images (2), rendering at computed DPI"


def test_reason_string_tricky_color() -> None:
    images = [ImageInfo(width=600, height=100, color="cmyk", is_mask=False)]
    reason = _build_render_reason(images, 500, 400)
    assert reason == "Tricky color space (cmyk), rendering"


def test_reason_string_text_plus_image() -> None:
    images = [ImageInfo(width=600, height=100, color="rgb", is_mask=False)]
    reason = _build_render_reason(images, 500, 400, has_text=True)
    assert reason == "Text + image page, rendering to preserve layout"


def test_debug_logging_for_render_dpi(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.DEBUG)

    images = [ImageInfo(width=1000, height=2000, color="cmyk", is_mask=False)]
    page_info = PageInfo(width_pts=500.0, height_pts=500.0)

    decide_processing_mode(
        images, page_info, min_width=500, dpi_text=100, force_render=False
    )

    assert (
        "Image 1000x2000: width_dpi=144.00, height_dpi=288.00 -> candidate=288.00"
        in caplog.text
    )
    assert "Selected render DPI: 288.00" in caplog.text


# --- Property Test for codebase-improvements ---


# Feature: codebase-improvements, Property: keep_blank rendering
@settings(max_examples=100)
@given(
    dpi_text=st.integers(min_value=DPI_MIN, max_value=DPI_MAX),
    min_width=st.integers(min_value=1, max_value=5000),
    page_w=st.floats(
        min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False
    ),
    page_h=st.floats(
        min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_prop_keep_blank_rendering(
    dpi_text: int, min_width: int, page_w: float, page_h: float
) -> None:
    """A blank page (no non-mask images, no text) is RENDERED when keep_blank=True.

    Validates: Requirements — --keep-blank forces rendering of otherwise-blank
    pages. The keep_blank flag is the deciding factor: the same inputs with
    keep_blank=False yield BLANK, proving the flag governs the outcome.
    """
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)

    # keep_blank=True → RENDER with clamped dpi
    decision = decide_processing_mode(
        [],
        page_info,
        min_width,
        dpi_text,
        force_render=False,
        has_text=False,
        keep_blank=True,
    )

    assert decision.mode is ProcessingMode.RENDER
    assert DPI_MIN <= decision.dpi <= DPI_MAX
    # dpi_text is generated within [DPI_MIN, DPI_MAX], so clamp is a no-op
    assert decision.dpi == float(dpi_text)
    assert "keep-blank" in decision.reason

    # Contrast: same inputs with keep_blank=False → BLANK (flag is decisive)
    blank_decision = decide_processing_mode(
        [],
        page_info,
        min_width,
        dpi_text,
        force_render=False,
        has_text=False,
        keep_blank=False,
    )

    assert blank_decision.mode is ProcessingMode.BLANK


# --- Property Test for codebase-improvements ---


# A non-mask ImageInfo generator: masks (is_mask=True) are intentionally excluded
# because the BLANK decision only considers non-mask images.
_non_mask_image = st.builds(
    ImageInfo,
    width=st.integers(min_value=1, max_value=5000),
    height=st.integers(min_value=1, max_value=5000),
    color=st.sampled_from(["rgb", "gray", "cmyk", "devn", "sep"]),
    is_mask=st.just(False),
)

_page_info = st.builds(
    PageInfo,
    width_pts=st.floats(
        min_value=1.0, max_value=2000.0, allow_nan=False, allow_infinity=False
    ),
    height_pts=st.floats(
        min_value=1.0, max_value=2000.0, allow_nan=False, allow_infinity=False
    ),
)


# Feature: codebase-improvements, Property: BLANK decision logic
# Validates Requirements (BLANK detection).
@settings(max_examples=100)
@given(
    page_info=_page_info,
    min_width=st.integers(min_value=1, max_value=2000),
    dpi_text=st.integers(min_value=36, max_value=2400),
)
def test_blank_decision_empty_and_no_text_is_blank(
    page_info: PageInfo, min_width: int, dpi_text: int
) -> None:
    """Property A: no non-mask images + no text + keep_blank=False -> BLANK, dpi==0."""
    decision = decide_processing_mode(
        [],
        page_info,
        min_width,
        dpi_text,
        force_render=False,
        has_text=False,
        keep_blank=False,
    )

    assert decision.mode is ProcessingMode.BLANK
    assert decision.dpi == 0


# Feature: codebase-improvements, Property: BLANK decision logic
# Validates Requirements (BLANK detection).
@settings(max_examples=100)
@given(
    images=st.lists(_non_mask_image, min_size=1, max_size=5),
    has_text=st.booleans(),
    page_info=_page_info,
    min_width=st.integers(min_value=1, max_value=2000),
    dpi_text=st.integers(min_value=36, max_value=2400),
)
def test_blank_decision_images_or_text_is_not_blank(
    images: list[ImageInfo],
    has_text: bool,
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
) -> None:
    """Property B: >=1 non-mask image OR has_text=True -> mode != BLANK."""
    decision = decide_processing_mode(
        images,
        page_info,
        min_width,
        dpi_text,
        force_render=False,
        has_text=has_text,
        keep_blank=False,
    )

    assert decision.mode is not ProcessingMode.BLANK
