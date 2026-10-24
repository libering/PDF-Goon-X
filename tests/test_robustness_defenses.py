"""TDD tests for robustness defenses and anti-false-green invariants.

Covers:
1. Handling of missing jbig2dec without pipeline crashing (smooth fallback).
2. Proper detection of 1-bit Stencil Mask pages (must trigger RENDER, not blank SKIP/EXTRACT 0 files).
3. Anti-false-green guard: a page cannot claim clean success (error=None) if 0 files produced on a non-blank visual page.
"""

from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
from pypdf.errors import DependencyError
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, BooleanObject, NumberObject, DecodedStreamObject

from pdf_goon.analyze.session import PypdfSession
from pdf_goon.analyze.decide import decide_processing_mode
from pdf_goon.models import ImageInfo, PageInfo, ProcessingMode, Config
from pdf_goon.pipeline.page import _process_page
import pdf_goon.core  # ensure default backends registered


def create_stencil_mask_pdf(dest_path: Path) -> Path:
    """Create a synthetic PDF with a single 1-bit Stencil Mask image."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)

    # 1-bit monochrome data (16x16, 2 bytes per row * 16 rows = 32 bytes)
    img_data = b"\xAA\x55" * 16
    img_stream = DecodedStreamObject()
    img_stream.set_data(img_data)
    img_stream.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(16),
        NameObject("/Height"): NumberObject(16),
        NameObject("/BitsPerComponent"): NumberObject(1),
        NameObject("/ImageMask"): BooleanObject(True),
    })

    mask_ref = writer._add_object(img_stream)
    xobj_dict = DictionaryObject({NameObject("/MaskImg"): mask_ref})
    res_dict = DictionaryObject({NameObject("/XObject"): xobj_dict})
    page[NameObject("/Resources")] = res_dict

    with open(dest_path, "wb") as f:
        writer.write(f)
    return dest_path


def test_jbig2_missing_dependency_graceful_handling(tmp_path: Path):
    """RED TEST: When pypdf raises DependencyError on page.images iteration,

    PypdfSession.inspect_page must NOT crash, but catch and return safely.
    """
    pdf_path = tmp_path / "dummy.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    session = PypdfSession(pdf_path)

    # Simulate DependencyError during page.images access or iteration
    with patch("pypdf._page.PageObject.images", new_callable=MagicMock) as mock_prop:
        def failing_iter():
            raise DependencyError("jbig2dec binary is not available.")
            yield
        mock_prop.__iter__.side_effect = failing_iter

        # Must catch DependencyError and safely fallback, not crash
        images, mask_indices, has_text, page_info = session.inspect_page(1)
        assert isinstance(images, list)
        assert isinstance(mask_indices, list)


def test_stencil_mask_only_page_decides_render(tmp_path: Path):
    """RED TEST: A page containing only a 1-bit Stencil Mask must be detected

    and decided as ProcessingMode.RENDER (never SKIP or EXTRACT 0 files).
    """
    stencil_pdf = tmp_path / "stencil_only.pdf"
    create_stencil_mask_pdf(stencil_pdf)

    session = PypdfSession(stencil_pdf)
    images, mask_indices, has_text, page_info = session.inspect_page(1)
    session.close()

    decision = decide_processing_mode(
        images=images,
        page_info=page_info,
        min_width=100,
        dpi_text=300,
        force_render=False,
        has_text=has_text,
        keep_blank=False,
    )

    # Mask requires background rendering to be visible -> must be RENDER!
    assert decision.mode == ProcessingMode.RENDER, (
        f"Expected RENDER for stencil mask page, but got {decision.mode} (reason: {decision.reason})"
    )


def test_pipeline_prevents_false_green_on_zero_extract(tmp_path: Path):
    """RED TEST: If a non-blank page is processed with EXTRACT/RENDER mode but yields

    0 image files, _process_page must report an error, NOT error=None.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    config = Config(path=tmp_path, dpi_text=300, min_width=100, keep_blank=False)

    pdf_path = tmp_path / "dummy_image.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    # Mock extract backend that returns 0 files
    mock_extract = MagicMock()
    mock_extract.extract_images.return_value = []

    from pdf_goon.models import PageDecision
    mock_decision = PageDecision(
        mode=ProcessingMode.EXTRACT,
        dpi=0,
        reason="Mock extract decision"
    )
    mock_page_info = PageInfo(width_pts=200, height_pts=200)

    res = _process_page(
        pdf_path=pdf_path,
        page=1,
        total_pages=1,
        workspace=workspace,
        output_dir=out_dir,
        config=config,
        extract_backend=mock_extract,
        decision_info=(mock_decision, [], [], mock_page_info),
    )

    # Anti-false-green: non-blank mode yielding 0 output files must NOT be considered error-free!
    assert res.error is not None, "Anti-false-green violated: 0 files produced on EXTRACT mode without error"
