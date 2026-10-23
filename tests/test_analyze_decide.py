# tests.test_analyze_decide — Unit and property tests for decide_processing_mode and blank page detection

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.analyze import (
    _build_render_reason,
    decide_processing_mode,
)
from pdf_goon.models import (
    DPI_MAX,
    DPI_MIN,
    ImageInfo,
    PageInfo,
    ProcessingMode,
)


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


