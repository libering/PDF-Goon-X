"""End-to-end regression tests verifying the 5 critical boundary corpus types.

These synthetic fixtures simulate real-world publisher edge-cases without
requiring copyrighted, gigabyte-sized files in CI/CD environments:
1. Two-Page Spread (橫向跨頁大圖): Aspect ratio ~1.5 (landscape).
2. Bleed Margins (CropBox != MediaBox): Commercial print bleed margins.
3. Rotation Labels (/Rotate 90/270): Page rotation tag with upright embedded image.
4. Monochrome Bitmaps (1-bit scan): 1-bit scan without mask.
5. Vector/Text Overlay: Background image + Form XObject text overlay.
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image
import pytest

from pdf_goon.analyze.decide import decide_processing_mode
from pdf_goon.analyze.session import PypdfSession
from pdf_goon.core import process_single_pdf
from pdf_goon.models import Config, ProcessingMode
from tests.synthetic_fixtures import (
    make_bleed_margins_pdf,
    make_monochrome_1bit_pdf,
    make_rotated_page_pdf,
    make_two_page_spread_pdf,
    make_vector_overlay_pdf,
)


@pytest.fixture
def fast_config(tmp_path: Path) -> Config:
    return Config(
        path=tmp_path,
        optimize=False,
        margin_tolerance=3.0,
        min_width=500,
        dpi_text=300,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(exist_ok=True)
    return ws


def test_two_page_spread_extraction(
    tmp_path: Path, workspace: Path, fast_config: Config
) -> None:
    """Wide two-page spread (landscape) must be recognized as EXTRACT, not degraded to RENDER."""
    pdf_path = tmp_path / "spread.pdf"
    make_two_page_spread_pdf(pdf_path)

    with PypdfSession(pdf_path) as s:
        imgs, masks, has_text, pinfo = s.inspect_page(1)
        assert pinfo.width_pts == 1200.0 and pinfo.height_pts == 800.0
        assert len(imgs) == 1 and not imgs[0].has_rotation
        assert imgs[0].width == 2400 and imgs[0].height == 1600
        decision = decide_processing_mode(
            imgs, pinfo, fast_config.min_width, fast_config.dpi_text, False
        )
        assert decision.mode == ProcessingMode.EXTRACT

    res = process_single_pdf(pdf_path, workspace, fast_config)
    assert res.success is True and res.pages_processed == 1

    out_file = pdf_path.parent / pdf_path.stem / "001.jpg"
    assert out_file.exists()
    with Image.open(out_file) as im:
        assert im.size == (2400, 1600)


def test_bleed_margins_cropbox_extraction(
    tmp_path: Path, workspace: Path, fast_config: Config
) -> None:
    """Page with CropBox bleed margins must resolve visual bounds and choose EXTRACT."""
    pdf_path = tmp_path / "bleed.pdf"
    make_bleed_margins_pdf(pdf_path, bleed_pts=10.0)

    with PypdfSession(pdf_path) as s:
        imgs, masks, has_text, pinfo = s.inspect_page(1)
        assert pinfo.width_pts == 600.0 and pinfo.height_pts == 800.0
        assert len(imgs) == 1
        decision = decide_processing_mode(
            imgs, pinfo, fast_config.min_width, fast_config.dpi_text, False
        )
        assert decision.mode == ProcessingMode.EXTRACT

    res = process_single_pdf(pdf_path, workspace, fast_config)
    assert res.success is True and res.pages_processed == 1

    out_file = pdf_path.parent / pdf_path.stem / "001.jpg"
    assert out_file.exists()
    with Image.open(out_file) as im:
        assert im.size == (1240, 1640)


def test_rotated_page_render_preservation(
    tmp_path: Path, workspace: Path, fast_config: Config
) -> None:
    """Page with /Rotate 90 tag must trigger RENDER to preserve visual orientation."""
    pdf_path = tmp_path / "rotated.pdf"
    make_rotated_page_pdf(pdf_path, rotation=90)

    with PypdfSession(pdf_path) as s:
        imgs, masks, has_text, pinfo = s.inspect_page(1)
        assert imgs[0].has_rotation is True
        decision = decide_processing_mode(
            imgs, pinfo, fast_config.min_width, fast_config.dpi_text, False
        )
        assert decision.mode == ProcessingMode.RENDER

    res = process_single_pdf(pdf_path, workspace, fast_config)
    assert res.success is True and res.pages_processed == 1

    out_file = pdf_path.parent / pdf_path.stem / "001_r.png"
    assert out_file.exists()
    with Image.open(out_file) as im:
        # 600x800 page rotated 90 deg becomes landscape (width > height)
        assert im.width > im.height


def test_monochrome_1bit_lossless_extraction(
    tmp_path: Path, workspace: Path, fast_config: Config
) -> None:
    """1-bit monochrome scanned page must NOT be treated as mask and must EXTRACT."""
    pdf_path = tmp_path / "monochrome.pdf"
    make_monochrome_1bit_pdf(pdf_path)

    with PypdfSession(pdf_path) as s:
        imgs, masks, has_text, pinfo = s.inspect_page(1)
        assert len(imgs) == 1 and not imgs[0].is_mask
        assert imgs[0].color == "1"
        assert len(masks) == 0
        decision = decide_processing_mode(
            imgs, pinfo, fast_config.min_width, fast_config.dpi_text, False
        )
        assert decision.mode == ProcessingMode.EXTRACT

    res = process_single_pdf(pdf_path, workspace, fast_config)
    assert res.success is True and res.pages_processed == 1

    out_file = pdf_path.parent / pdf_path.stem / "001.png"
    assert out_file.exists()
    with Image.open(out_file) as im:
        assert im.size == (1200, 1600)
        assert im.mode in ("1", "L")


def test_vector_overlay_mixed_content_render(
    tmp_path: Path, workspace: Path, fast_config: Config
) -> None:
    """Background image with Form XObject text overlay must trigger RENDER (never EXTRACT)."""
    pdf_path = tmp_path / "overlay.pdf"
    make_vector_overlay_pdf(pdf_path)

    with PypdfSession(pdf_path) as s:
        imgs, masks, has_text, pinfo = s.inspect_page(1)
        assert has_text is True and len(imgs) == 1
        decision = decide_processing_mode(
            imgs,
            pinfo,
            fast_config.min_width,
            fast_config.dpi_text,
            False,
            has_text=has_text,
        )
        assert decision.mode == ProcessingMode.RENDER
        assert "Text + image page" in decision.reason

    res = process_single_pdf(pdf_path, workspace, fast_config)
    assert res.success is True and res.pages_processed == 1

    out_file = pdf_path.parent / pdf_path.stem / "001_r.png"
    assert out_file.exists()
    assert out_file.stat().st_size > 0
