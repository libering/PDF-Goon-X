# tests.test_core — Tests for pdf_goon.core

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.core import _process_page, process_batch, process_single_pdf
from pdf_goon.models import (
    Config,
    PageDecision,
    PageInfo,
    PageResult,
    ProcessingMode,
    ProcessResult,
    make_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path: Path, **overrides: object) -> Config:
    """Create a Config pointing to tmp_path with sensible test defaults."""
    defaults = {
        "path": str(tmp_path),
        "verbose": False,
        "replace": False,
        "optimize": False,
        "recursive": False,
    }
    defaults.update(overrides)
    return make_config(**defaults)


def _create_pdf_files(tmp_path: Path, count: int) -> list[Path]:
    """Create N dummy .pdf files in tmp_path."""
    files: list[Path] = []
    for i in range(count):
        f = tmp_path / f"doc_{i:03d}.pdf"
        f.write_bytes(b"%PDF-1.4 dummy")
        files.append(f)
    return files


# Common mock targets in pdf_goon.core
_PATCH_CHECK_POPPLER = "pdf_goon.core.check_poppler_available"
_PATCH_GET_PAGE_COUNT = "pdf_goon.core.get_page_count"
_PATCH_GET_IMAGE_DATA = "pdf_goon.core.get_image_data"
_PATCH_GET_PAGE_INFO = "pdf_goon.core.get_page_info"
_PATCH_DECIDE_MODE = "pdf_goon.core.decide_processing_mode"
_PATCH_EXTRACT_IMAGES = "pdf_goon.core.extract_images"
_PATCH_OPTIMIZE_IMAGE = "pdf_goon.core.optimize_image"
_PATCH_RENDER_PAGE = "pdf_goon.core.render_page"
_PATCH_WORKSPACE = "pdf_goon.core.workspace_context"


# ---------------------------------------------------------------------------
# Feature: pdf-goon-refactor, Property 2: Batch processing is resilient to
# individual failures
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    num_valid=st.integers(min_value=1, max_value=5),
    num_invalid=st.integers(min_value=1, max_value=5),
)
def test_batch_resilient_to_individual_failures(
    num_valid: int, num_invalid: int
) -> None:
    """ProcessResult returned for every file; valid files still processed.

    **Validates: Requirements 5.3, 1.6**
    """
    import shutil
    import tempfile

    # Create a unique temp dir per hypothesis example (tmp_path is shared)
    work_dir = Path(tempfile.mkdtemp(prefix="pbt_core_"))
    try:
        # Create valid PDF files
        valid_files = []
        for i in range(num_valid):
            f = work_dir / f"valid_{i:03d}.pdf"
            f.write_bytes(b"%PDF-1.4 dummy")
            valid_files.append(f)

        # Create invalid (non-existent) paths — just names, no file on disk
        invalid_files = []
        for i in range(num_invalid):
            f = work_dir / f"invalid_{i:03d}.pdf"
            # Don't create the file — it won't exist
            invalid_files.append(f)

        # We need all files to appear in the glob. Create them all, then delete
        # the invalid ones after glob resolves. Instead, create all files and
        # mock get_page_count to return None for "invalid" ones.
        for f in invalid_files:
            f.write_bytes(b"%PDF-1.4 dummy")

        total_files = num_valid + num_invalid

        def mock_page_count(pdf_path: Path) -> int | None:
            if pdf_path.name.startswith("invalid_"):
                return None  # Simulates unreadable PDF
            return 1

        config = _make_config(work_dir)

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, side_effect=mock_page_count),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            results = process_batch(config)

        # A ProcessResult for every file
        assert len(results) == total_files

        # Valid files succeeded
        valid_results = [r for r in results if r.pdf_path.name.startswith("valid_")]
        for r in valid_results:
            assert r.success is True

        # Invalid files failed gracefully
        invalid_results = [r for r in results if r.pdf_path.name.startswith("invalid_")]
        for r in invalid_results:
            assert r.success is False
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Feature: pdf-goon-refactor, Property 3: Expected failures return
# Result_Value, never raise
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    filename=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=10,
    )
)
def test_expected_failures_return_result_never_raise(
    filename: str,
) -> None:
    """Non-existent path returns ProcessResult(success=False), no exception.

    **Validates: Requirements 16.5, 5.3**
    """
    import tempfile

    work_dir = Path(tempfile.mkdtemp(prefix="pbt_core_fail_"))
    try:
        non_existent = work_dir / f"{filename}.pdf"
        # Ensure it does NOT exist
        if non_existent.exists():
            non_existent.unlink()

        config = _make_config(work_dir)

        # process_single_pdf should return a failure result, not raise
        result = process_single_pdf(
            non_existent,
            workspace=work_dir,
            config=config,
        )

        assert isinstance(result, ProcessResult)
        assert result.success is False
        assert result.error is not None
        assert len(result.error) > 0
    finally:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)


@settings(max_examples=100)
@given(num_pages=st.just(0))
def test_zero_pages_returns_failure_result(num_pages: int) -> None:
    """PDF with zero pages returns ProcessResult(success=False), no exception.

    **Validates: Requirements 16.5, 5.3**
    """
    import tempfile

    work_dir = Path(tempfile.mkdtemp(prefix="pbt_core_zero_"))
    try:
        pdf_file = work_dir / "zero_pages.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")

        config = _make_config(work_dir)

        with patch(_PATCH_GET_PAGE_COUNT, return_value=0):
            result = process_single_pdf(
                pdf_file,
                workspace=work_dir,
                config=config,
            )

        assert isinstance(result, ProcessResult)
        assert result.success is False
        assert result.error is not None
        assert "zero" in result.error.lower()
    finally:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Feature: pdf-goon-refactor, Property 9: Progress callback receives correct
# sequential indices
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(num_files=st.integers(min_value=1, max_value=8))
def test_progress_callback_sequential_indices(
    num_files: int,
) -> None:
    """Callback invoked N times with current from 1..N and total=N.

    **Validates: Requirements 9.4, 9.2**
    """
    import tempfile

    work_dir = Path(tempfile.mkdtemp(prefix="pbt_core_prog_"))
    try:
        # Create N PDF files
        for i in range(num_files):
            (work_dir / f"file_{i:03d}.pdf").write_bytes(b"%PDF-1.4 dummy")

        config = _make_config(work_dir)

        # Recording callback
        invocations: list[tuple[int, int, Path]] = []

        def recording_callback(current: int, total: int, path: Path) -> None:
            invocations.append((current, total, path))

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, return_value=1),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            process_batch(config, progress_callback=recording_callback)

        # Callback invoked exactly N times
        assert len(invocations) == num_files

        # current ranges from 1..N sequentially, total always == N
        for idx, (current, total, path) in enumerate(invocations):
            assert current == idx + 1
            assert total == num_files
    finally:
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Unit Tests for core (Task 10.5)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Feature: pdf-goon-hardening, Bug B2: render prefix collides with extraction glob
# ---------------------------------------------------------------------------


class TestRenderPrefixCollision:
    """Tests for bug B2 — render files must not be caught by extraction glob.

    **Validates: Requirements B2 (AC1)**
    """

    def test_render_prefix_not_caught_by_extraction_glob(
        self, tmp_path: Path
    ) -> None:
        """Render file prefix must NOT start with extraction prefix.

        Bug: extraction uses 'page_{page}_tmp' and rendering uses
        'page_{page}_tmp-{page}'. The glob 'page_1_tmp*' catches both.
        After the fix, render should use a distinct prefix (e.g. 'render_1_tmp').
        """
        page = 1
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")
        config = _make_config(tmp_path)

        # Track the prefix passed to render_page
        render_prefix_used: list[Path] = []
        original_render_page = MagicMock()

        def capture_render_prefix(
            pdf_path: Path,
            page_num: int,
            output_prefix: Path,
            dpi: float,
            page_info: object,
        ) -> list[Path]:
            render_prefix_used.append(output_prefix)
            # Simulate render producing a file
            out_file = output_prefix.parent / f"{output_prefix.name}.png"
            out_file.write_bytes(b"fake png")
            return [out_file]

        extraction_prefix_name = f"page_{page}_tmp"

        with (
            patch(_PATCH_GET_PAGE_COUNT, return_value=1),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.RENDER, 150, "force render"),
            ),
            patch(_PATCH_RENDER_PAGE, side_effect=capture_render_prefix),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            process_single_pdf(pdf_file, workspace=tmp_path, config=config)

        # Verify render was called
        assert len(render_prefix_used) == 1, "render_page should have been called once"

        # The render prefix name must NOT start with the extraction prefix
        # This is the core of bug B2: currently render uses 'page_1_tmp-1'
        # which starts with 'page_1_tmp', so extraction glob catches it.
        render_name = render_prefix_used[0].name
        assert not render_name.startswith(extraction_prefix_name), (
            f"Render prefix '{render_name}' starts with extraction prefix "
            f"'{extraction_prefix_name}' — glob collision! "
            f"Render files would be caught by extraction glob pattern "
            f"'{extraction_prefix_name}*'"
        )


# ---------------------------------------------------------------------------
# Feature: pdf-goon-hardening, Bug B1: sub-image index regex not anchored
# ---------------------------------------------------------------------------


class TestSubImageIndexRegex:
    r"""Tests for bug B1 — sub-image index must use the TAIL dash-number.

    When multiple images exist for the same page, _finalize_page_files uses a
    regex to extract the sub-image index from the filename. The unanchored
    regex ``r"-(\d+)"`` matches the FIRST ``-number`` in the filename, which
    is wrong when the filename contains multiple ``-number`` segments.

    **Validates: Requirements B1 (AC1, AC2)**
    """

    def test_multi_image_page_uses_tail_index(self, tmp_path: Path) -> None:
        r"""Sub-image naming uses the LAST dash-number (file index), not the first.

        Scenario: pdfimages extracts two images from page 1. The workspace
        files have the pattern `page_1_tmp-<N>-<INDEX>.png` (where an
        intermediate component introduces an extra dash-number).

        The first file `page_1_tmp-3-000.png` is renamed to `001.png`.
        The second file `page_1_tmp-3-001.png` tries `001.png` → exists →
        falls into the sub-index branch.

        With the unanchored regex `r"-(\d+)"`, it matches `-3` → group(1)="3",
        producing `001_3.png` (WRONG).

        With the anchored regex `r"-(\d+)\.[^.]+$"`, it matches `-001` →
        group(1)="001", producing `001_001.png` (CORRECT).
        """
        from pdf_goon.core import _finalize_page_files
        from pdf_goon.models import make_config

        workspace = tmp_path / "work"
        workspace.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create two files simulating pdfimages output with an extra
        # dash-number component in the prefix (e.g., intermediate format)
        file_a = workspace / "page_1_tmp-3-000.png"
        file_b = workspace / "page_1_tmp-3-001.png"
        file_a.write_bytes(b"fake png A")
        file_b.write_bytes(b"fake png B")

        config = make_config(path=str(tmp_path), verbose=False, replace=False, optimize=False, recursive=False)

        _finalize_page_files(
            generated_files=[file_a, file_b],
            mask_indices=[],
            was_rendered=False,
            page=1,
            output_dir=output_dir,
            config=config,
        )

        output_files = sorted(f.name for f in output_dir.iterdir())

        # The first file should be 001.png (base name for page 1)
        # The second file should use the TAIL index "001" → 001_001.png
        # NOT "3" from the first dash-number match → 001_3.png
        assert "001.png" in output_files, (
            f"Expected '001.png' in output, got: {output_files}"
        )
        assert "001_001.png" in output_files, (
            f"Expected '001_001.png' (tail index) in output, got: {output_files}. "
            f"If '001_3.png' is present, the regex matched the wrong '-number' group."
        )


# ---------------------------------------------------------------------------
# Unit Tests for core (Task 10.5)
# ---------------------------------------------------------------------------


class TestProcessSinglePdf:
    """Unit tests for process_single_pdf."""

    def test_missing_file_returns_failure(self, tmp_path: Path) -> None:
        """Guard clause returns failure for non-existent file.

        **Validates: Requirements 16.8, 5.3**
        """
        config = _make_config(tmp_path)
        missing = tmp_path / "ghost.pdf"

        result = process_single_pdf(missing, workspace=tmp_path, config=config)

        assert result.success is False
        assert result.error == "File not found"

    def test_unreadable_pdf_returns_failure(self, tmp_path: Path) -> None:
        """Guard clause returns failure when page count is None.

        **Validates: Requirements 16.8, 5.3**
        """
        config = _make_config(tmp_path)
        pdf_file = tmp_path / "bad.pdf"
        pdf_file.write_bytes(b"not a real pdf")

        with patch(_PATCH_GET_PAGE_COUNT, return_value=None):
            result = process_single_pdf(pdf_file, workspace=tmp_path, config=config)

        assert result.success is False
        assert "page count" in result.error.lower()

    def test_zero_pages_returns_failure(self, tmp_path: Path) -> None:
        """Guard clause returns failure for zero-page PDF.

        **Validates: Requirements 16.8, 5.3**
        """
        config = _make_config(tmp_path)
        pdf_file = tmp_path / "empty.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch(_PATCH_GET_PAGE_COUNT, return_value=0):
            result = process_single_pdf(pdf_file, workspace=tmp_path, config=config)

        assert result.success is False
        assert "zero" in result.error.lower()

    def test_successful_processing_with_mocked_pipeline(
        self, tmp_path: Path
    ) -> None:
        """Full pipeline succeeds with mocked analyze/extract/optimize.

        **Validates: Requirements 10.1, 5.3**
        """
        config = _make_config(tmp_path)
        pdf_file = tmp_path / "good.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        with (
            patch(_PATCH_GET_PAGE_COUNT, return_value=2),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
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


class TestProcessBatch:
    """Unit tests for process_batch."""

    def test_batch_continues_after_individual_failure(
        self, tmp_path: Path
    ) -> None:
        """Batch processes all files even when some fail.

        **Validates: Requirements 5.3, 1.6**
        """
        # Create 3 files: first will fail, others succeed
        (tmp_path / "a_fail.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "b_ok.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "c_ok.pdf").write_bytes(b"%PDF-1.4")

        def mock_page_count(pdf_path: Path) -> int | None:
            if "fail" in pdf_path.name:
                return None
            return 1

        config = _make_config(tmp_path)

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, side_effect=mock_page_count),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            results = process_batch(config)

        assert len(results) == 3

        failed = [r for r in results if not r.success]
        succeeded = [r for r in results if r.success]

        assert len(failed) == 1
        assert "fail" in failed[0].pdf_path.name
        assert len(succeeded) == 2

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        """No PDFs in directory returns empty results list.

        **Validates: Requirements 5.3**
        """
        config = _make_config(tmp_path)

        with patch(_PATCH_CHECK_POPPLER, return_value=[]):
            results = process_batch(config)

        assert results == []

    def test_progress_callback_invocation_order(self, tmp_path: Path) -> None:
        """Progress callback receives sequential indices in correct order.

        **Validates: Requirements 9.2**
        """
        _create_pdf_files(tmp_path, 3)
        config = _make_config(tmp_path)

        invocations: list[tuple[int, int, Path]] = []

        def callback(current: int, total: int, path: Path) -> None:
            invocations.append((current, total, path))

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, return_value=1),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            process_batch(config, progress_callback=callback)

        assert len(invocations) == 3
        assert invocations[0][0] == 1
        assert invocations[1][0] == 2
        assert invocations[2][0] == 3
        # total is always 3
        for _, total, _ in invocations:
            assert total == 3

    def test_filename_containing_delete_marker_is_not_excluded(
        self, tmp_path: Path
    ) -> None:
        """PDF whose filename contains '!delete' substring is NOT excluded.

        The filter should only exclude files under a *directory* named '!delete',
        not files whose name happens to contain the substring.

        **Validates: Requirements B3 (AC2)**
        """
        # Create a PDF with "!delete" in its filename (not a directory)
        pdf_file = tmp_path / "report!delete-final.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")

        config = _make_config(tmp_path)

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, return_value=1),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            results = process_batch(config)

        # The file should be included — not filtered out
        assert len(results) == 1
        assert results[0].pdf_path.name == "report!delete-final.pdf"
        assert results[0].success is True

    def test_pdf_under_delete_directory_is_excluded(
        self, tmp_path: Path
    ) -> None:
        """PDF inside a directory named '!delete' is excluded from batch.

        This is the positive case: the exclusion filter correctly skips files
        that live under a !delete/ directory, regardless of whether the check
        uses str(f) or f.parts.

        **Validates: Requirements B3 (AC1)**
        """
        # Create directory structure: !delete/somefile.pdf AND normal.pdf
        delete_dir = tmp_path / "!delete"
        delete_dir.mkdir()
        (delete_dir / "somefile.pdf").write_bytes(b"%PDF-1.4 dummy")
        (tmp_path / "normal.pdf").write_bytes(b"%PDF-1.4 dummy")

        config = _make_config(tmp_path, recursive=True)

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, return_value=1),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            results = process_batch(config)

        # Only normal.pdf should be processed — !delete/somefile.pdf is excluded
        assert len(results) == 1
        assert results[0].pdf_path.name == "normal.pdf"
        assert results[0].success is True

    def test_batch_handles_exception_in_single_pdf(
        self, tmp_path: Path
    ) -> None:
        """Unexpected exception in process_single_pdf is caught per-file.

        **Validates: Requirements 5.3**
        """
        _create_pdf_files(tmp_path, 2)
        config = _make_config(tmp_path)

        call_count = 0

        def mock_page_count(pdf_path: Path) -> int | None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("unexpected OS error")
            return 1

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, side_effect=mock_page_count),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            results = process_batch(config)

        # Both files get results — first failed, second succeeded
        assert len(results) == 2
        assert results[0].success is False
        assert "unexpected" in results[0].error.lower()
        assert results[1].success is True


# ---------------------------------------------------------------------------
# Feature: pdf-goon-hardening, A1: _process_page returns PageResult
# ---------------------------------------------------------------------------


class TestProcessPageReturnsPageResult:
    """Tests that _process_page returns a PageResult with correct fields.

    **Validates: Requirements A1 (AC1)**
    """

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
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
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

    def test_process_page_returns_page_result_render_mode(
        self, tmp_path: Path
    ) -> None:
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
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [])),
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
