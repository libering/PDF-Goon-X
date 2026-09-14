# tests.test_backends — Tests for pdf_goon.backends (Backend Protocol)

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pdf_goon.backends import (
    AnalyzeBackend,
    ExtractBackend,
    PypdfAnalyzeBackend,
    PypdfExtractBackend,
    Pypdfium2RenderBackend,
    RenderBackend,
)
from pdf_goon.core import process_batch
from pdf_goon.models import Config, ImageInfo, PageInfo, make_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, **overrides: object) -> Config:
    """Create a Config pointing to tmp_path with sensible test defaults."""
    defaults: dict[str, object] = {
        "path": str(tmp_path),
        "verbose": False,
        "replace": False,
        "optimize": False,
        "recursive": False,
    }
    defaults.update(overrides)
    return make_config(**defaults)


def _create_pdf(tmp_path: Path, name: str = "doc.pdf") -> Path:
    """Create a single dummy .pdf file so process_batch discovers it."""
    f = tmp_path / name
    f.write_bytes(b"%PDF-1.4 dummy")
    return f


# ---------------------------------------------------------------------------
# Requirement 4.1 / 4.8: Protocol isinstance checks via @runtime_checkable
# ---------------------------------------------------------------------------


def test_default_analyze_backend_is_analyze_backend() -> None:
    """PypdfAnalyzeBackend structurally satisfies AnalyzeBackend.

    **Validates: Requirements 4.1**
    """
    assert isinstance(PypdfAnalyzeBackend(), AnalyzeBackend)


def test_default_extract_backend_is_extract_backend() -> None:
    """PypdfExtractBackend structurally satisfies ExtractBackend.

    **Validates: Requirements 4.1**
    """
    assert isinstance(PypdfExtractBackend(), ExtractBackend)


def test_default_render_backend_is_render_backend() -> None:
    """Pypdfium2RenderBackend structurally satisfies RenderBackend.

    **Validates: Requirements 4.1**
    """
    assert isinstance(Pypdfium2RenderBackend(), RenderBackend)


def test_incomplete_object_is_not_analyze_backend() -> None:
    """An object missing protocol methods fails the runtime_checkable check.

    Guards against a false-positive isinstance that would let a broken
    backend slip through injection.

    **Validates: Requirements 4.1**
    """

    class NotABackend:
        def get_page_count(self, pdf_path: Path) -> int | None:
            return 0

        # Missing get_image_data and get_page_info.

    assert not isinstance(NotABackend(), AnalyzeBackend)


def test_duck_typed_object_satisfies_extract_backend() -> None:
    """A structurally-compatible object satisfies ExtractBackend without
    inheritance — the point of a runtime_checkable Protocol.

    **Validates: Requirements 4.1**
    """

    class DuckExtract:
        def extract_images(
            self, pdf_path: Path, page_num: int, output_prefix: Path
        ) -> list[Path]:
            return []

    assert isinstance(DuckExtract(), ExtractBackend)


# ---------------------------------------------------------------------------
# Requirement 4.5: Default implementations delegate to analyze.py / extract.py
# ---------------------------------------------------------------------------


def test_analyze_backend_get_page_count_delegates() -> None:
    """PypdfAnalyzeBackend.get_page_count delegates to analyze.get_page_count.

    **Validates: Requirements 4.5**
    """
    with patch("pdf_goon.analyze.get_page_count", return_value=7) as mock_fn:
        result = PypdfAnalyzeBackend().get_page_count(Path("x.pdf"))

    assert result == 7
    mock_fn.assert_called_once_with(Path("x.pdf"))


def test_analyze_backend_get_image_data_delegates() -> None:
    """PypdfAnalyzeBackend.get_image_data delegates to analyze.get_image_data.

    **Validates: Requirements 4.5**
    """
    payload: tuple[list[ImageInfo], list[str], bool] = (
        [ImageInfo(width=10, height=20, color="rgb", is_mask=False)],
        ["image"],
        False,
    )
    with patch("pdf_goon.analyze.get_image_data", return_value=payload) as mock_fn:
        result = PypdfAnalyzeBackend().get_image_data(Path("x.pdf"), 3)

    assert result == payload
    mock_fn.assert_called_once_with(Path("x.pdf"), 3)


def test_analyze_backend_get_page_info_delegates() -> None:
    """PypdfAnalyzeBackend.get_page_info delegates to analyze.get_page_info.

    **Validates: Requirements 4.5**
    """
    page_info = PageInfo(width_pts=595.0, height_pts=842.0)
    with patch("pdf_goon.analyze.get_page_info", return_value=page_info) as mock_fn:
        result = PypdfAnalyzeBackend().get_page_info(Path("x.pdf"), 1)

    assert result == page_info
    mock_fn.assert_called_once_with(Path("x.pdf"), 1)


def test_extract_backend_delegates() -> None:
    """PypdfExtractBackend.extract_images delegates to extract.extract_images.

    **Validates: Requirements 4.5**
    """
    produced = [Path("out-000.png")]
    with patch("pdf_goon.extract.extract_images", return_value=produced) as mock_fn:
        result = PypdfExtractBackend().extract_images(Path("x.pdf"), 2, Path("out"))

    assert result == produced
    mock_fn.assert_called_once_with(Path("x.pdf"), 2, Path("out"))


def test_render_backend_delegates() -> None:
    """Pypdfium2RenderBackend.render_page delegates to extract.render_page.

    **Validates: Requirements 4.5**
    """
    page_info = PageInfo(width_pts=595.0, height_pts=842.0)
    produced = [Path("page-1.png")]
    with patch("pdf_goon.extract.render_page", return_value=produced) as mock_fn:
        result = Pypdfium2RenderBackend().render_page(
            Path("x.pdf"), 1, Path("out"), 300.0, page_info
        )

    assert result == produced
    mock_fn.assert_called_once_with(Path("x.pdf"), 1, Path("out"), 300.0, page_info)


# ---------------------------------------------------------------------------
# Requirement 4.6 / 4.7: Custom backend injection via process_batch()
# ---------------------------------------------------------------------------


class _SpyAnalyzeBackend:
    """Records calls and short-circuits processing by reporting no pages.

    Returning ``None`` from get_page_count makes process_single_pdf bail out
    early with a structured failure — this lets us prove the injected backend
    is actually used without touching extraction, rendering, or threads.
    """

    def __init__(self) -> None:
        self.page_count_calls: list[Path] = []

    def get_page_count(self, pdf_path: Path) -> int | None:
        self.page_count_calls.append(pdf_path)
        return None

    def get_image_data(
        self, pdf_path: Path, page_num: int
    ) -> tuple[list[ImageInfo], list[str], bool]:
        return ([], [], False)

    def get_page_info(self, pdf_path: Path, page_num: int) -> PageInfo:
        return PageInfo(width_pts=595.0, height_pts=842.0)


def test_process_batch_uses_injected_analyze_backend(tmp_path: Path) -> None:
    """process_batch routes analysis through the injected AnalyzeBackend.

    **Validates: Requirements 4.6**
    """
    pdf_path = _create_pdf(tmp_path)
    config = _make_config(tmp_path)
    spy = _SpyAnalyzeBackend()

    results = process_batch(config, analyze_backend=spy)

    # The spy was consulted for the discovered PDF.
    assert spy.page_count_calls == [pdf_path.resolve()]
    # And its None return propagated to a structured failure result.
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error == "Cannot read page count"


def test_injected_backend_takes_precedence_over_default(tmp_path: Path) -> None:
    """A custom backend overrides the default; module functions are not called.

    **Validates: Requirements 4.6, 4.7**
    """
    _create_pdf(tmp_path)
    config = _make_config(tmp_path)
    spy = _SpyAnalyzeBackend()

    with patch("pdf_goon.core.get_page_count") as default_fn:
        process_batch(config, analyze_backend=spy)

    # The injected backend absorbed the analysis; the default was bypassed.
    assert spy.page_count_calls
    default_fn.assert_not_called()


def test_process_batch_defaults_when_no_backend_given(tmp_path: Path) -> None:
    """Without overrides, process_batch falls back to default analysis path.

    **Validates: Requirements 4.6**
    """
    _create_pdf(tmp_path)
    config = _make_config(tmp_path)

    # Patch at the module boundary the default backend delegates through.
    with patch("pdf_goon.core.get_page_count", return_value=None) as default_fn:
        results = process_batch(config)

    default_fn.assert_called_once()
    assert len(results) == 1
    assert results[0].success is False
