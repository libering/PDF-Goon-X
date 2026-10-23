# tests.test_core — Tests for pdf_goon.core single-page, pipeline, and equivalence

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.core import (
    _finalize_extracted_files,
    _finalize_page_files,
    _finalize_rendered_file,
    _process_page,
    process_single_pdf,
)
from pdf_goon.models import (
    Config,
    PageDecision,
    PageInfo,
    PageResult,
    ProcessingMode,
    ProcessResult,
    make_config,
)

_PATCH_GET_PAGE_COUNT = "pdf_goon.core.get_page_count"
_PATCH_GET_IMAGE_DATA = "pdf_goon.core.get_image_data"
_PATCH_GET_PAGE_INFO = "pdf_goon.core.get_page_info"
_PATCH_DECIDE_MODE = "pdf_goon.core.decide_processing_mode"
_PATCH_EXTRACT_IMAGES = "pdf_goon.core.extract_images"
_PATCH_OPTIMIZE_IMAGE = "pdf_goon.core.optimize_image"
_PATCH_RENDER_PAGE = "pdf_goon.core.render_page"


def _make_config(tmp_path: Path, **overrides: object) -> Config:
    defaults = {
        "path": str(tmp_path),
        "verbose": False,
        "replace": False,
        "optimize": False,
        "recursive": False,
    }
    defaults.update(overrides)
    return make_config(**defaults)


# ---------------------------------------------------------------------------
# Single PDF Guard Clauses & Expected Failures
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=10,
    )
)
def test_expected_failures_return_result_never_raise(filename: str) -> None:
    """Non-existent path returns ProcessResult(success=False), no exception."""
    work_dir = Path(tempfile.mkdtemp(prefix="pbt_core_fail_"))
    try:
        non_existent = work_dir / f"{filename}.pdf"
        if non_existent.exists():
            non_existent.unlink()

        config = _make_config(work_dir)
        result = process_single_pdf(non_existent, workspace=work_dir, config=config)

        assert isinstance(result, ProcessResult)
        assert result.success is False
        assert result.error is not None
        assert len(result.error) > 0
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@settings(max_examples=100)
@given(num_pages=st.just(0))
def test_zero_pages_returns_failure_result(num_pages: int) -> None:
    """PDF with zero pages returns ProcessResult(success=False), no exception."""
    work_dir = Path(tempfile.mkdtemp(prefix="pbt_core_zero_"))
    try:
        pdf_file = work_dir / "zero_pages.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")

        config = _make_config(work_dir)
        with patch(_PATCH_GET_PAGE_COUNT, return_value=0):
            result = process_single_pdf(pdf_file, workspace=work_dir, config=config)

        assert isinstance(result, ProcessResult)
        assert result.success is False
        assert result.error is not None
        assert "zero" in result.error.lower()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


class TestProcessSinglePdf:
    """Unit tests for process_single_pdf."""

    def test_missing_file_returns_failure(self, tmp_path: Path) -> None:
        """Guard clause returns failure for non-existent file."""
        config = _make_config(tmp_path)
        missing = tmp_path / "ghost.pdf"
        result = process_single_pdf(missing, workspace=tmp_path, config=config)
        assert result.success is False
        assert result.error == "File not found"

    def test_unreadable_pdf_returns_failure(self, tmp_path: Path) -> None:
        """Guard clause returns failure when page count is None."""
        config = _make_config(tmp_path)
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"not a real pdf")

        with patch(_PATCH_GET_PAGE_COUNT, return_value=None):
            result = process_single_pdf(pdf_file, workspace=tmp_path, config=config)

        assert result.success is False
        assert result.error is not None
        assert "page count" in result.error.lower()

    def test_zero_pages_returns_failure(self, tmp_path: Path) -> None:
        """Guard clause returns failure for zero-page PDF."""
        config = _make_config(tmp_path)
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch(_PATCH_GET_PAGE_COUNT, return_value=0):
            result = process_single_pdf(pdf_file, workspace=tmp_path, config=config)

        assert result.success is False
        assert result.error is not None
        assert "zero" in result.error.lower()

    def test_successful_processing_with_mocked_pipeline(self, tmp_path: Path) -> None:
        """Full pipeline succeeds with mocked analyze/extract/optimize."""
        config = _make_config(tmp_path)
        pdf_file = tmp_path / "good.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        with (
            patch(_PATCH_GET_PAGE_COUNT, return_value=2),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            result = process_single_pdf(pdf_file, workspace=tmp_path, config=config)

        assert result.success is True
        assert result.pages_processed == 2
        assert result.error is None


class TestProcessPageReturnsPageResult:
    """Tests that _process_page returns a PageResult with correct fields."""

    def test_process_page_returns_page_result_extract_mode(
        self, tmp_path: Path
    ) -> None:
        """_process_page returns PageResult with correct page_num and mode (EXTRACT)."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        config = _make_config(tmp_path)
        page = 3

        with (
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "extract test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            result = _process_page(pdf_file, page, 5, workspace, output_dir, config)

        assert isinstance(result, PageResult)
        assert result.page_num == page
        assert result.mode == ProcessingMode.EXTRACT

    def test_process_page_returns_page_result_render_mode(self, tmp_path: Path) -> None:
        """_process_page returns PageResult with correct page_num and mode (RENDER)."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        config = _make_config(tmp_path)
        page = 7

        with (
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.RENDER, 150, "render test"),
            ),
            patch(_PATCH_RENDER_PAGE, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            result = _process_page(pdf_file, page, 10, workspace, output_dir, config)

        assert isinstance(result, PageResult)
        assert result.page_num == page
        assert result.mode == ProcessingMode.RENDER


# ---------------------------------------------------------------------------
# Behavioral Equivalence Helpers
# ---------------------------------------------------------------------------


def _setup_dual_workspaces(work_dir: Path) -> tuple[Path, Path, Path, Path]:
    ws_dispatch = work_dir / "dispatch"
    ws_dispatch.mkdir()
    out_dispatch = work_dir / "out_dispatch"
    out_dispatch.mkdir()

    ws_direct = work_dir / "direct"
    ws_direct.mkdir()
    out_direct = work_dir / "out_direct"
    out_direct.mkdir()
    return ws_dispatch, out_dispatch, ws_direct, out_direct


def _assert_render_delegation(work_dir: Path, page: int, suffix: str) -> None:
    ws_dispatch, out_dispatch, ws_direct, out_direct = _setup_dual_workspaces(work_dir)

    file_dispatch = ws_dispatch / f"render_{page}_tmp{suffix}"
    file_dispatch.write_bytes(b"\x89PNG fake render output")
    file_direct = ws_direct / f"render_{page}_tmp{suffix}"
    file_direct.write_bytes(b"\x89PNG fake render output")

    config = make_config(path=str(work_dir), optimize=False)
    result_dispatch = _finalize_page_files(
        generated_files=[file_dispatch],
        mask_indices=[],
        was_rendered=True,
        page=page,
        output_dir=out_dispatch,
        config=config,
    )
    result_direct = _finalize_rendered_file(
        generated_files=[file_direct],
        page=page,
        output_dir=out_direct,
        config=config,
    )

    assert len(result_dispatch) == len(result_direct) == 1
    assert [f.name for f in result_dispatch] == [f.name for f in result_direct]
    assert result_dispatch[0].name == f"{page:03d}_r{suffix}"
    assert result_dispatch[0].read_bytes() == result_direct[0].read_bytes()


def _assert_extract_delegation(
    work_dir: Path, page: int, suffix: str, num_images: int, has_mask: bool
) -> None:
    ws_dispatch, out_dispatch, ws_direct, out_direct = _setup_dual_workspaces(work_dir)

    files_dispatch: list[Path] = []
    files_direct: list[Path] = []
    for i in range(num_images):
        content = f"image data {i}".encode()
        fd = ws_dispatch / f"page_{page}_tmp-{i:03d}{suffix}"
        fd.write_bytes(content)
        files_dispatch.append(fd)

        fr = ws_direct / f"page_{page}_tmp-{i:03d}{suffix}"
        fr.write_bytes(content)
        files_direct.append(fr)

    mask_indices = ["000"] if (has_mask and num_images > 1) else []
    config = make_config(path=str(work_dir), optimize=False)

    result_dispatch = _finalize_page_files(
        generated_files=files_dispatch,
        mask_indices=mask_indices,
        was_rendered=False,
        page=page,
        output_dir=out_dispatch,
        config=config,
    )
    result_direct = _finalize_extracted_files(
        generated_files=files_direct,
        mask_indices=mask_indices,
        page=page,
        output_dir=out_direct,
        config=config,
    )

    assert len(result_dispatch) == len(result_direct)
    assert sorted(f.name for f in result_dispatch) == sorted(f.name for f in result_direct)
    for fd, fr in zip(
        sorted(result_dispatch, key=lambda p: p.name),
        sorted(result_direct, key=lambda p: p.name),
    ):
        assert fd.read_bytes() == fr.read_bytes()


def _assert_dispatcher_routing(work_dir: Path, was_rendered: bool) -> None:
    workspace = work_dir / "work"
    workspace.mkdir()
    output_dir = work_dir / "output"
    output_dir.mkdir()

    page = 5
    suffix = ".png"
    if was_rendered:
        test_file = workspace / f"render_{page}_tmp{suffix}"
    else:
        test_file = workspace / f"page_{page}_tmp-000{suffix}"
    test_file.write_bytes(b"\x89PNG test routing")

    config = make_config(path=str(work_dir), optimize=False)
    result = _finalize_page_files(
        generated_files=[test_file],
        mask_indices=[],
        was_rendered=was_rendered,
        page=page,
        output_dir=output_dir,
        config=config,
    )
    assert len(result) == 1
    if was_rendered:
        assert "_r" in result[0].name
    else:
        assert "_r" not in result[0].name


class TestFinalizationBehavioralEquivalence:
    """Dispatcher delegates correctly based on was_rendered flag."""

    @settings(max_examples=100, deadline=None)
    @given(
        page=st.integers(min_value=1, max_value=999),
        suffix=st.sampled_from([".png", ".jpg", ".jpeg"]),
    )
    def test_render_path_delegates_to_finalize_rendered(
        self, page: int, suffix: str
    ) -> None:
        """RENDER path: dispatcher output == _finalize_rendered_file() output."""
        work_dir = Path(tempfile.mkdtemp(prefix="pbt_fin_render_"))
        try:
            _assert_render_delegation(work_dir, page, suffix)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    @settings(max_examples=100, deadline=None)
    @given(
        page=st.integers(min_value=1, max_value=999),
        suffix=st.sampled_from([".png", ".jpg", ".jpeg"]),
        num_images=st.integers(min_value=1, max_value=4),
        has_mask=st.booleans(),
    )
    def test_extract_path_delegates_to_finalize_extracted(
        self, page: int, suffix: str, num_images: int, has_mask: bool
    ) -> None:
        """EXTRACT path: dispatcher output == _finalize_extracted_files() output."""
        work_dir = Path(tempfile.mkdtemp(prefix="pbt_fin_extract_"))
        try:
            _assert_extract_delegation(work_dir, page, suffix, num_images, has_mask)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    @settings(max_examples=100, deadline=None)
    @given(was_rendered=st.booleans())
    def test_dispatcher_routing_is_deterministic(self, was_rendered: bool) -> None:
        """Dispatcher always routes to the correct sub-function based on flag."""
        work_dir = Path(tempfile.mkdtemp(prefix="pbt_fin_route_"))
        try:
            _assert_dispatcher_routing(work_dir, was_rendered)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Recording Backends & BLANK Page Test
# ---------------------------------------------------------------------------


class _RecordingAnalyzeBackend:
    def get_page_count(self, pdf_path: Path) -> int | None:
        return 1

    def get_image_data(self, pdf_path: Path, page_num: int) -> tuple[list, list, bool]:
        return ([], [], False)

    def get_page_info(self, pdf_path: Path, page_num: int) -> PageInfo:
        return PageInfo(width_pts=612.0, height_pts=792.0)


class _RecordingExtractBackend:
    def __init__(self) -> None:
        self.called = False

    def extract_images(
        self, pdf_path: Path, page_num: int, output_prefix: Path
    ) -> list[Path]:
        self.called = True
        return []


class _RecordingRenderBackend:
    def __init__(self) -> None:
        self.called = False

    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
        dpi: float,
        page_info: object,
        pdf_data: bytes | None = None,
    ) -> list[Path]:
        self.called = True
        return []


def _assert_blank_page_skip(work_dir: Path, page: int) -> None:
    workspace = work_dir / "workspace"
    workspace.mkdir()
    output_dir = work_dir / "output"
    output_dir.mkdir()

    pdf_file = work_dir / "blank.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    config = make_config(
        path=str(work_dir),
        keep_blank=False,
        optimize=False,
    )

    analyze = _RecordingAnalyzeBackend()
    extract = _RecordingExtractBackend()
    render = _RecordingRenderBackend()

    result = _process_page(
        pdf_file,
        page,
        page,
        workspace,
        output_dir,
        config,
        analyze_backend=analyze,
        extract_backend=extract,
        render_backend=render,
    )

    assert extract.called is False
    assert render.called is False
    assert isinstance(result, PageResult)
    assert result.mode == ProcessingMode.BLANK
    assert result.files_produced == ()
    assert result.error is None


@settings(max_examples=100)
@given(page=st.integers(min_value=1, max_value=500))
def test_blank_page_skip_behavior(page: int) -> None:
    """BLANK pages short-circuit: no backend calls, empty PageResult, no error."""
    work_dir = Path(tempfile.mkdtemp(prefix="pbt_blank_skip_"))
    try:
        _assert_blank_page_skip(work_dir, page)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
