"""End-to-end integration tests using authentic, real PDF files.

Covers:
- Real full-page manga scan -> EXTRACT
- Real manga with 1.5pt white border -> EXTRACT (D1 bugfix validation)
- Real manga with 15pt margin -> RENDER
- Real scanned book with invisible OCR text layer (3 Tr) -> EXTRACT (D2 bugfix validation)
- Real scanned page with visible typography -> RENDER
- Real 1-bit monochrome scanned novel -> EXTRACT (D3 bugfix validation, no silent loss)
- Real multi-page mixed manga book -> Batch session dispatch
"""

from __future__ import annotations

from pathlib import Path
import pytest

from pdf_goon.core import process_single_pdf
from pdf_goon.models import Config
from tests.real_pdf_fixtures import (
    make_blank_pdf,
    make_form_xobject_text_pdf,
    make_full_page_manga_pdf,
    make_image_with_smask_pdf,
    make_large_margin_15pt_pdf,
    make_light_novel_complete_volume_pdf,
    make_monochrome_1bit_pdf,
    make_multi_images_pdf,
    make_multi_page_mixed_book_pdf,
    make_novel_with_chapter_ornament_pdf,
    make_ocr_invisible_text_pdf,
    make_pure_text_novel_pdf,
    make_pure_text_pdf,
    make_visible_text_pdf,
    make_white_border_1_5pt_pdf,
)


@pytest.fixture
def base_config(tmp_path: Path) -> Config:
    return Config(
        path=tmp_path,
        optimize=False,  # Fast testing without external optimizer
        margin_tolerance=3.0,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(exist_ok=True)
    return ws


def test_real_full_page_manga_extract(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    pdf_path = tmp_path / "manga.pdf"
    make_full_page_manga_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001.jpg"
    assert files[0].stat().st_size > 0


def test_real_white_border_1_5pt_extract(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies D1 fix: 1.5pt white border (<= 3.0pt tolerance) extracts losslessly."""
    pdf_path = tmp_path / "border_1_5pt.pdf"
    make_white_border_1_5pt_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001.jpg"
    assert files[0].stat().st_size > 0


def test_real_large_margin_15pt_render(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies that large margins (> 3.0pt) trigger RENDER to preserve page background."""
    pdf_path = tmp_path / "margin_15pt.pdf"
    make_large_margin_15pt_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001_r.png"
    assert files[0].stat().st_size > 0


def test_real_scanned_book_invisible_ocr_extract(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies D2 fix: Text Rendering Mode 3 (invisible OCR text) does not trigger RENDER."""
    pdf_path = tmp_path / "invisible_ocr.pdf"
    make_ocr_invisible_text_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001.jpg"
    assert files[0].stat().st_size > 0


def test_real_visible_typography_render(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies that visible text (0 Tr) triggers RENDER to preserve text."""
    pdf_path = tmp_path / "visible_text.pdf"
    make_visible_text_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001_r.png"
    assert files[0].stat().st_size > 0


def test_real_monochrome_1bit_scanned_extract(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies D3 fix: 1-bit monochrome scanned pages are extracted and NOT lost."""
    pdf_path = tmp_path / "monochrome_1bit.pdf"
    make_monochrome_1bit_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001.png"
    assert files[0].stat().st_size > 0


def test_real_blank_page_skip(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    pdf_path = tmp_path / "blank.pdf"
    make_blank_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 0


def test_real_multi_images_page_render(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    pdf_path = tmp_path / "multi_images.pdf"
    make_multi_images_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001_r.png"


def test_real_pure_text_render(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    pdf_path = tmp_path / "pure_text.pdf"
    make_pure_text_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001_r.png"


def test_real_multi_page_mixed_book_pipeline(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """End-to-end multi-page session testing batch extraction & rendering across 5 pages."""
    pdf_path = tmp_path / "mixed_book.pdf"
    make_multi_page_mixed_book_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 5

    out_dir = pdf_path.parent / pdf_path.stem
    files = sorted(list(out_dir.glob("*")), key=lambda p: p.name)

    # 4 files generated (Page 5 was blank and skipped):
    # Page 1: 001.jpg (extracted cover)
    # Page 2: 002_r.png (rendered typography)
    # Page 3: 003.png (extracted 1-bit monochrome)
    # Page 4: 004.jpg (extracted scan with OCR)
    assert [f.name for f in files] == [
        "001.jpg",
        "002_r.png",
        "003.png",
        "004.jpg",
    ]


def test_real_downloaded_cmyk_pdf(workspace: Path, base_config: Config) -> None:
    """Verifies D9: CMYK image PDF from py-pdf is processed cleanly via RENDER."""
    pdf_path = Path("real_test_pdfs/cmyk-image.pdf")
    if not pdf_path.exists():
        pytest.skip("real_test_pdfs/cmyk-image.pdf not downloaded")
    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1
    out_dir = pdf_path.parent / pdf_path.stem
    assert (out_dir / "001_r.png").exists()


def test_real_downloaded_multipage_pdf(workspace: Path, base_config: Config) -> None:
    """Verifies multi-page real PDF from pypdfium2."""
    pdf_path = Path("real_test_pdfs/pypdfium2-multipage.pdf")
    if not pdf_path.exists():
        pytest.skip("real_test_pdfs/pypdfium2-multipage.pdf not downloaded")
    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 3
    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*.png"))
    assert len(files) == 3


def test_real_downloaded_w3c_dummy_pdf(workspace: Path, base_config: Config) -> None:
    """Verifies W3C dummy text PDF is rendered cleanly."""
    pdf_path = Path("real_test_pdfs/w3c-dummy.pdf")
    if not pdf_path.exists():
        pytest.skip("real_test_pdfs/w3c-dummy.pdf not downloaded")
    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1
    out_dir = pdf_path.parent / pdf_path.stem
    assert (out_dir / "001_r.png").exists()


# ---------------------------------------------------------------------------
# Pure Text (Novel / 小說) & Light Novel Tests
# ---------------------------------------------------------------------------


def test_real_pure_text_novel_multi_page_batch_render(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies that an authentic 10-page pure text novel renders all pages.

    Tests continuous batch worker rendering across multiple novel text pages,
    ensuring each page produces a high-resolution PNG with fallback DPI.
    """
    pdf_path = tmp_path / "time_machine_novel.pdf"
    make_pure_text_novel_pdf(pdf_path, num_pages=10)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 10

    out_dir = pdf_path.parent / pdf_path.stem
    rendered_files = sorted(list(out_dir.glob("*.png")), key=lambda p: p.name)
    assert len(rendered_files) == 10

    # Verify filenames and non-empty content
    for idx, f in enumerate(rendered_files, 1):
        assert f.name == f"{idx:03d}_r.png"
        assert f.stat().st_size > 0


def test_real_pure_text_novel_custom_dpi_scaling(
    tmp_path: Path, workspace: Path
) -> None:
    """Verifies that pure text novel page renders strictly at the configured dpi_text.

    For A5 format (420 x 595 pt):
    - At DPI 300: target_w = round(420 * 300 / 72) = 1750, target_h = round(595 * 300 / 72) = 2479
    - At DPI 600: target_w = round(420 * 600 / 72) = 3500, target_h = round(595 * 600 / 72) = 4958
    """
    from PIL import Image

    pdf_path = tmp_path / "dpi_test_novel.pdf"
    make_pure_text_novel_pdf(pdf_path, num_pages=1)

    # 1. Run at DPI 300
    config_300 = Config(path=tmp_path, optimize=False, dpi_text=300)
    result_300 = process_single_pdf(pdf_path, workspace, config_300)
    assert result_300.success is True
    out_dir_300 = pdf_path.parent / pdf_path.stem
    img_300 = Image.open(out_dir_300 / "001_r.png")
    w_300, h_300 = img_300.size
    img_300.close()
    assert abs(w_300 - int(420 * 300 / 72)) <= 2
    assert abs(h_300 - int(595 * 300 / 72)) <= 2

    # Clean up output dir for 600 run
    import shutil

    shutil.rmtree(out_dir_300)

    # 2. Run at DPI 600
    config_600 = Config(path=tmp_path, optimize=False, dpi_text=600)
    result_600 = process_single_pdf(pdf_path, workspace, config_600)
    assert result_600.success is True
    img_600 = Image.open(out_dir_300 / "001_r.png")
    w_600, h_600 = img_600.size
    img_600.close()
    assert abs(w_600 - int(420 * 600 / 72)) <= 2
    assert abs(h_600 - int(595 * 600 / 72)) <= 2

    # Verify scaling is exactly 2x
    assert abs(w_600 - 2 * w_300) <= 2
    assert abs(h_600 - 2 * h_300) <= 2


def test_real_novel_with_small_ornament_icon_render(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies that a novel page with text and small chapter header ornament renders whole page.

    The ornament image is 200px wide (< min_width 500px).
    Rule: small images must not be extracted alone; page layout must be preserved via RENDER.
    """
    pdf_path = tmp_path / "novel_ornament.pdf"
    make_novel_with_chapter_ornament_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001_r.png"
    assert files[0].stat().st_size > 0


def test_real_light_novel_complete_volume_dispatch(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies full 10-page light novel volume workflow.

    - Pages 1-2: Color cover & pinup inserts -> EXTRACT (.jpg)
    - Pages 3-6: TOC, chapter ornament header, chapter body text -> RENDER (.png)
    - Page 7: Blank chapter break -> BLANK (skipped)
    - Pages 8-9: Chapter 2 body, afterword -> RENDER (.png)
    - Page 10: Blank end page -> BLANK (skipped)
    """
    pdf_path = tmp_path / "light_novel_vol1.pdf"
    make_light_novel_complete_volume_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 10

    out_dir = pdf_path.parent / pdf_path.stem
    files = sorted(list(out_dir.glob("*")), key=lambda p: p.name)

    # Exactly 8 files produced (pages 7 and 10 skipped as blank):
    expected_filenames = [
        "001.jpg",  # Cover (extracted)
        "002.jpg",  # Pinup insert (extracted)
        "003_r.png",  # Table of contents (rendered)
        "004_r.png",  # Chapter 1 ornament & text (rendered)
        "005_r.png",  # Chapter 1 text body (rendered)
        "006_r.png",  # Chapter 1 text body (rendered)
        "008_r.png",  # Chapter 2 text body (rendered)
        "009_r.png",  # Afterword (rendered)
    ]
    assert [f.name for f in files] == expected_filenames


def test_real_downloaded_pdflatex_4_pages_text_novel(
    workspace: Path, base_config: Config
) -> None:
    """Verifies downloaded 4-page LaTeX text book from py-pdf."""
    pdf_path = Path("real_test_pdfs/pdflatex-4-pages.pdf")
    if not pdf_path.exists():
        pytest.skip("real_test_pdfs/pdflatex-4-pages.pdf not downloaded")
    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 4
    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*.png"))
    assert len(files) == 4


def test_real_downloaded_crazyones_pdfa_text(
    workspace: Path, base_config: Config
) -> None:
    """Verifies downloaded Steve Jobs text PDF/A from py-pdf."""
    pdf_path = Path("real_test_pdfs/crazyones-pdfa.pdf")
    if not pdf_path.exists():
        pytest.skip("real_test_pdfs/crazyones-pdfa.pdf not downloaded")
    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1
    out_dir = pdf_path.parent / pdf_path.stem
    assert (out_dir / "001_r.png").exists()


def test_real_downloaded_multicolumn_text(workspace: Path, base_config: Config) -> None:
    """Verifies downloaded multi-column text document from py-pdf."""
    pdf_path = Path("real_test_pdfs/multicolumn.pdf")
    if not pdf_path.exists():
        pytest.skip("real_test_pdfs/multicolumn.pdf not downloaded")
    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 3
    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*.png"))
    assert len(files) == 3


def test_real_image_with_smask_extract(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies that an image with an attached /SMask is extracted losslessly, never BLANK."""
    pdf_path = tmp_path / "smask_manga.pdf"
    make_image_with_smask_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*"))
    assert len(files) == 1
    assert files[0].name == "001.png"
    assert files[0].stat().st_size > 0


def test_real_form_xobject_text_render(
    tmp_path: Path, workspace: Path, base_config: Config
) -> None:
    """Verifies that text nested inside a Form XObject is detected and rendered, never BLANK."""
    pdf_path = tmp_path / "form_xobject_novel.pdf"
    make_form_xobject_text_pdf(pdf_path)

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 1

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*.png"))
    assert len(files) == 1
    assert files[0].name == "001_r.png"
    assert files[0].stat().st_size > 0


