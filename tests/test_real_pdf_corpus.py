"""Empirical verification on local real-world copyrighted PDF corpus.

Requires the real test PDF corpus files. Run with:
    pytest -m corpus
"""

from __future__ import annotations

from pathlib import Path
import pytest

from pdf_goon.core import process_single_pdf
from pdf_goon.models import Config


@pytest.fixture
def base_config(tmp_path: Path) -> Config:
    return Config(
        path=tmp_path,
        optimize=False,
        margin_tolerance=3.0,
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(exist_ok=True)
    return ws


@pytest.mark.corpus
def test_real_corpus_egihid_extract(workspace: Path, base_config: Config) -> None:
    """Regression test: egihid.pdf must extract all pages without dropping any as BLANK."""
    candidates = [
        Path(r"C:\Users\user\Downloads\Documents\egihid.pdf"),
        Path("real_test_pdfs/egihid.pdf"),
    ]
    pdf_path = next((p for p in candidates if p.exists()), None)
    if pdf_path is None:
        pytest.skip("egihid.pdf not found in local environment")

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 128

    out_dir = pdf_path.parent / pdf_path.stem
    files = sorted(list(out_dir.glob("*")))
    assert len(files) == 128
    assert files[0].name == "001.png"
    assert files[1].name == "002.png"


@pytest.mark.corpus
def test_real_corpus_comic3_spread_alignment(
    workspace: Path, base_config: Config
) -> None:
    """Verifies comic3.pdf maintains 22/22 page continuity and extracts pure-white page 2."""
    candidates = [
        Path(r"C:\Users\user\Downloads\Documents\コミック3.pdf"),
        Path("real_test_pdfs/コミック3.pdf"),
    ]
    pdf_path = next((p for p in candidates if p.exists()), None)
    if pdf_path is None:
        pytest.skip("コミック3.pdf not found in local environment")

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 22

    out_dir = pdf_path.parent / pdf_path.stem
    files = sorted(list(out_dir.glob("*")))
    assert len(files) == 22
    assert files[0].name == "001.png"
    assert files[1].name == "002.png"
    assert files[-1].name == "022.png"


@pytest.mark.corpus
def test_real_corpus_novel_spread_render(
    workspace: Path, base_config: Config
) -> None:
    """Verifies Japanese novel spread with Form XObjects renders all pages without dropping as BLANK."""
    candidates = [
        Path("real_test_pdfs/novel_spread_a5.pdf"),
        Path(r"C:\Users\user\Downloads\Documents\目がさめたら_A5見開き版.pdf"),
    ]
    pdf_path = next((p for p in candidates if p.exists()), None)
    if pdf_path is None:
        doc_dir = Path(r"C:\Users\user\Downloads\Documents")
        matches = list(doc_dir.glob("*A5*.pdf"))
        pdf_path = matches[0] if matches else None

    if pdf_path is None:
        pytest.skip("novel spread PDF not found in local environment")

    result = process_single_pdf(pdf_path, workspace, base_config)
    assert result.success is True
    assert result.pages_processed == 54

    out_dir = pdf_path.parent / pdf_path.stem
    files = list(out_dir.glob("*_r.png"))
    assert len(files) == 54
