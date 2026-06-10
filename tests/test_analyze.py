# tests.test_analyze — Tests for pdf_goon.analyze

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.analyze import (
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
    SubprocessError,
)


# Feature: pdf-goon-refactor, Property 1: DPI computation is always within valid bounds
# **Validates: Requirements 6.4, 7.1, 7.2**
@settings(max_examples=100)
@given(
    page_width_pts=st.floats(
        min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False
    ),
    image_width=st.integers(min_value=1, max_value=50000),
    min_width=st.integers(min_value=1, max_value=5000),
    dpi_text=st.integers(min_value=1, max_value=5000),
    force_render=st.booleans(),
)
def test_dpi_always_within_valid_bounds(
    page_width_pts: float,
    image_width: int,
    min_width: int,
    dpi_text: int,
    force_render: bool,
) -> None:
    """decide_processing_mode always produces DPI in [DPI_MIN, DPI_MAX] for RENDER, or 0 for EXTRACT."""
    images = [ImageInfo(width=image_width, height=100, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=page_width_pts, height_pts=800.0)

    decision = decide_processing_mode(images, page_info, min_width, dpi_text, force_render)

    if decision.mode is ProcessingMode.RENDER:
        assert DPI_MIN <= decision.dpi <= DPI_MAX, (
            f"DPI {decision.dpi} out of bounds [{DPI_MIN}, {DPI_MAX}]"
        )
    else:
        assert decision.dpi == 0, (
            f"EXTRACT mode should have dpi=0, got {decision.dpi}"
        )


# --- Unit tests for get_page_count ---


DUMMY_PDF = Path("/tmp/test.pdf")


def test_get_page_count_returns_correct_count() -> None:
    """get_page_count extracts page count from pdfinfo output."""
    def fake_run(cmd: list[str]) -> str:
        return "Title:    My PDF\nPages:    5\nCreator:  Test\n"

    result = get_page_count(DUMMY_PDF, run=fake_run)
    assert result == 5


def test_get_page_count_returns_none_on_subprocess_error() -> None:
    """get_page_count returns None when subprocess raises SubprocessError."""
    def failing_run(cmd: list[str]) -> str:
        raise SubprocessError(tool="pdfinfo", exit_code=1, stderr="bad pdf")

    result = get_page_count(DUMMY_PDF, run=failing_run)
    assert result is None


def test_get_page_count_returns_none_when_no_pages_line() -> None:
    """get_page_count returns None when output lacks a 'Pages:' line."""
    def fake_run(cmd: list[str]) -> str:
        return "Title:    My PDF\nCreator:  Test\n"

    result = get_page_count(DUMMY_PDF, run=fake_run)
    assert result is None


# --- Unit tests for get_image_data ---


PDFIMAGES_LIST_OUTPUT = """\
page   num  type   width  height  color  comp bpc  enc interp  object ID x-ppi y-ppi
--------------------------------------------------------------------------------------------
   1     0  image   1200    800   rgb     3    8  jpeg   no        10  0   150   150
   1     1  smask   1200    800   gray    1    8  image  no        10  0   150   150
"""


def test_get_image_data_parses_normal_images() -> None:
    """get_image_data correctly parses image entries from pdfimages -list output."""
    def fake_run(cmd: list[str]) -> str:
        return PDFIMAGES_LIST_OUTPUT

    images, masks = get_image_data(DUMMY_PDF, 1, run=fake_run)

    assert len(images) == 1
    assert images[0].width == 1200
    assert images[0].height == 800
    assert images[0].color == "rgb"
    assert images[0].is_mask is False


def test_get_image_data_identifies_smask_as_mask() -> None:
    """get_image_data identifies smask entries and records their indices."""
    def fake_run(cmd: list[str]) -> str:
        return PDFIMAGES_LIST_OUTPUT

    _, masks = get_image_data(DUMMY_PDF, 1, run=fake_run)

    assert len(masks) == 1
    assert masks[0] == "001"  # smask is the second entry (index 1), zero-padded


def test_get_image_data_returns_empty_on_subprocess_error() -> None:
    """get_image_data returns empty lists when subprocess fails."""
    def failing_run(cmd: list[str]) -> str:
        raise SubprocessError(tool="pdfimages", exit_code=1, stderr="error")

    images, masks = get_image_data(DUMMY_PDF, 1, run=failing_run)

    assert images == []
    assert masks == []


# --- Unit tests for get_page_info ---


def test_get_page_info_parses_dimensions() -> None:
    """get_page_info parses page dimensions with C-float simulation."""
    def fake_run(cmd: list[str]) -> str:
        return "Page    1 size: 612.0 x 792.0\nOther: data\n"

    info = get_page_info(DUMMY_PDF, 1, run=fake_run)

    # C-float simulation: 612.0 and 792.0 should round-trip cleanly
    assert abs(info.width_pts - 612.0) < 0.01
    assert abs(info.height_pts - 792.0) < 0.01


def test_get_page_info_returns_zero_on_failure() -> None:
    """get_page_info returns (0.0, 0.0) when subprocess fails."""
    def failing_run(cmd: list[str]) -> str:
        raise SubprocessError(tool="pdfinfo", exit_code=1, stderr="error")

    info = get_page_info(DUMMY_PDF, 1, run=failing_run)

    assert info.width_pts == 0.0
    assert info.height_pts == 0.0


# --- Unit tests for decide_processing_mode ---


def test_decide_single_large_image_extracts() -> None:
    """Single large image wider than min_width triggers EXTRACT mode."""
    images = [ImageInfo(width=1200, height=800, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(images, page_info, min_width=500, dpi_text=400, force_render=False)

    assert decision.mode is ProcessingMode.EXTRACT
    assert decision.dpi == 0


def test_decide_multiple_images_renders() -> None:
    """Multiple non-mask images trigger RENDER mode."""
    images = [
        ImageInfo(width=1200, height=800, color="rgb", is_mask=False),
        ImageInfo(width=600, height=400, color="rgb", is_mask=False),
    ]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(images, page_info, min_width=500, dpi_text=400, force_render=False)

    assert decision.mode is ProcessingMode.RENDER
    assert DPI_MIN <= decision.dpi <= DPI_MAX


def test_decide_force_render_overrides() -> None:
    """force_render=True always triggers RENDER mode regardless of image count."""
    images = [ImageInfo(width=1200, height=800, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(images, page_info, min_width=500, dpi_text=400, force_render=True)

    assert decision.mode is ProcessingMode.RENDER
    assert DPI_MIN <= decision.dpi <= DPI_MAX


def test_decide_small_image_icon_renders_at_dpi_text() -> None:
    """Single small image (icon) narrower than min_width triggers RENDER at dpi_text."""
    images = [ImageInfo(width=100, height=100, color="rgb", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(images, page_info, min_width=500, dpi_text=400, force_render=False)

    assert decision.mode is ProcessingMode.RENDER
    assert decision.dpi == 400.0


def test_decide_tricky_color_renders() -> None:
    """Single image with tricky color (cmyk) triggers RENDER mode."""
    images = [ImageInfo(width=1200, height=800, color="cmyk", is_mask=False)]
    page_info = PageInfo(width_pts=612.0, height_pts=792.0)

    decision = decide_processing_mode(images, page_info, min_width=500, dpi_text=400, force_render=False)

    assert decision.mode is ProcessingMode.RENDER
    assert DPI_MIN <= decision.dpi <= DPI_MAX
