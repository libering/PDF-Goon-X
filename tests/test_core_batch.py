# tests.test_core_batch — Batch processing tests for pdf_goon.core

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.core import process_batch
from pdf_goon.models import (
    Config,
    PageDecision,
    PageInfo,
    ProcessingMode,
    ProcessResult,
    make_config,
)

# ---------------------------------------------------------------------------
# Helpers & Mocks
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


_PATCH_CHECK_POPPLER = "pdf_goon.core.get_page_count"
_PATCH_GET_PAGE_COUNT = "pdf_goon.core.get_page_count"
_PATCH_GET_IMAGE_DATA = "pdf_goon.core.get_image_data"
_PATCH_GET_PAGE_INFO = "pdf_goon.core.get_page_info"
_PATCH_DECIDE_MODE = "pdf_goon.core.decide_processing_mode"
_PATCH_EXTRACT_IMAGES = "pdf_goon.core.extract_images"
_PATCH_OPTIMIZE_IMAGE = "pdf_goon.core.optimize_image"


def _setup_resilience_test_files(
    work_dir: Path, num_valid: int, num_invalid: int
) -> None:
    for i in range(num_valid):
        (work_dir / f"valid_{i:03d}.pdf").write_bytes(b"%PDF-1.4 dummy")
    for i in range(num_invalid):
        (work_dir / f"invalid_{i:03d}.pdf").write_bytes(b"%PDF-1.4 dummy")


def _run_mocked_batch(work_dir: Path) -> list[ProcessResult]:
    def mock_page_count(pdf_path: Path) -> int | None:
        if pdf_path.name.startswith("invalid_"):
            return None
        return 1

    config = _make_config(work_dir)
    with (
        patch(_PATCH_CHECK_POPPLER, return_value=[]),
        patch(_PATCH_GET_PAGE_COUNT, side_effect=mock_page_count),
        patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
        patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
        patch(
            _PATCH_DECIDE_MODE,
            return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
        ),
        patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
        patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
    ):
        return process_batch(config)


# ---------------------------------------------------------------------------
# Property Tests for process_batch
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
    work_dir = Path(tempfile.mkdtemp(prefix="pbt_core_"))
    try:
        _setup_resilience_test_files(work_dir, num_valid, num_invalid)
        results = _run_mocked_batch(work_dir)

        assert len(results) == num_valid + num_invalid
        for r in results:
            if r.pdf_path.name.startswith("valid_"):
                assert r.success is True
            elif r.pdf_path.name.startswith("invalid_"):
                assert r.success is False
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@settings(max_examples=100)
@given(num_files=st.integers(min_value=1, max_value=8))
def test_progress_callback_sequential_indices(num_files: int) -> None:
    """Callback invoked N times with current from 1..N and total=N.

    **Validates: Requirements 9.4, 9.2**
    """
    work_dir = Path(tempfile.mkdtemp(prefix="pbt_core_prog_"))
    try:
        for i in range(num_files):
            (work_dir / f"file_{i:03d}.pdf").write_bytes(b"%PDF-1.4 dummy")

        config = _make_config(work_dir)
        invocations: list[tuple[int, int, Path]] = []

        def recording_callback(current: int, total: int, path: Path) -> None:
            invocations.append((current, total, path))

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, return_value=1),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            process_batch(config, progress_callback=recording_callback)

        assert len(invocations) == num_files
        for idx, (current, total, _path) in enumerate(invocations):
            assert current == idx + 1
            assert total == num_files
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Unit Tests for process_batch
# ---------------------------------------------------------------------------


class TestProcessBatch:
    """Unit tests for process_batch."""

    def test_batch_continues_after_individual_failure(self, tmp_path: Path) -> None:
        """Batch processes all files even when some fail.

        **Validates: Requirements 5.3, 1.6**
        """
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
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
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
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
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
        for _, total, _ in invocations:
            assert total == 3

    def test_filename_containing_delete_marker_is_not_excluded(
        self, tmp_path: Path
    ) -> None:
        """PDF whose filename contains '!delete' substring is NOT excluded.

        **Validates: Requirements B3 (AC2)**
        """
        pdf_file = tmp_path / "report!delete-final.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy")
        config = _make_config(tmp_path)

        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, return_value=1),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            results = process_batch(config)

        assert len(results) == 1
        assert results[0].pdf_path.name == "report!delete-final.pdf"
        assert results[0].success is True

    def test_pdf_under_delete_directory_is_excluded(self, tmp_path: Path) -> None:
        """PDF inside a directory named '!delete' is excluded from batch.

        **Validates: Requirements B3 (AC1)**
        """
        delete_dir = tmp_path / "!delete"
        delete_dir.mkdir()
        (delete_dir / "somefile.pdf").write_bytes(b"%PDF-1.4 dummy")
        (tmp_path / "normal.pdf").write_bytes(b"%PDF-1.4 dummy")

        config = _make_config(tmp_path, recursive=True)
        with (
            patch(_PATCH_CHECK_POPPLER, return_value=[]),
            patch(_PATCH_GET_PAGE_COUNT, return_value=1),
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            results = process_batch(config)

        assert len(results) == 1
        assert results[0].pdf_path.name == "normal.pdf"
        assert results[0].success is True

    def test_batch_handles_exception_in_single_pdf(self, tmp_path: Path) -> None:
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
            patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
            patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
            patch(
                _PATCH_DECIDE_MODE,
                return_value=PageDecision(ProcessingMode.EXTRACT, 0, "test"),
            ),
            patch(_PATCH_EXTRACT_IMAGES, return_value=[]),
            patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
        ):
            results = process_batch(config)

        assert len(results) == 2
        assert results[0].success is False
        assert results[0].error is not None
        assert "unexpected" in results[0].error.lower()
        assert results[1].success is True
