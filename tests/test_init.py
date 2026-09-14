# tests.test_init — Tests for pdf_goon public API (__init__.py)

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pdf_goon
from pdf_goon.models import Config, ProcessResult


# ---------------------------------------------------------------------------
# Unit Tests for public API (Task 11.2)
# ---------------------------------------------------------------------------


class TestImportNoSideEffects:
    """Verify that importing pdf_goon has no side effects.

    **Validates: Requirements 1.2, 1.5**
    """

    def test_import_exposes_expected_symbols(self) -> None:
        """Importing pdf_goon exposes Config, ProcessResult, VERSION, process."""
        assert hasattr(pdf_goon, "Config")
        assert hasattr(pdf_goon, "ProcessResult")
        assert hasattr(pdf_goon, "VERSION")
        assert hasattr(pdf_goon, "process")

    def test_import_does_not_write_stdout(self, capsys) -> None:
        """Importing pdf_goon produces no stdout output."""
        import importlib

        importlib.reload(pdf_goon)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_all_exports_match_expected(self) -> None:
        """__all__ contains exactly the expected public symbols."""
        assert set(pdf_goon.__all__) == {
            "Config",
            "ProcessResult",
            "VERSION",
            "process",
        }


class TestProcessDelegatesToCore:
    """Verify process() constructs Config and delegates to process_batch.

    **Validates: Requirements 1.2, 1.5**
    """

    @patch("pdf_goon.process_batch")
    @patch("pdf_goon.make_config")
    def test_process_constructs_config_and_calls_process_batch(
        self, mock_make_config: MagicMock, mock_process_batch: MagicMock, tmp_path: Path
    ) -> None:
        """process() calls make_config with kwargs and passes result to process_batch."""
        fake_config = Config(path=tmp_path)
        mock_make_config.return_value = fake_config
        mock_process_batch.return_value = []

        result = pdf_goon.process(
            path=str(tmp_path),
            verbose=True,
            replace=False,
            optimize=True,
            dpi_text=300,
            min_width=600,
            recursive=True,
            force_render=False,
            debug=False,
        )

        # make_config was called with the correct keyword arguments
        mock_make_config.assert_called_once_with(
            path=str(tmp_path),
            verbose=True,
            replace=False,
            optimize=True,
            dpi_text=300,
            min_width=600,
            recursive=True,
            force_render=False,
            debug=False,
            keep_blank=False,
        )

        # process_batch was called with the constructed config
        mock_process_batch.assert_called_once_with(fake_config, progress_callback=None)

        assert result == []

    @patch("pdf_goon.process_batch")
    @patch("pdf_goon.make_config")
    def test_process_returns_process_batch_results(
        self, mock_make_config: MagicMock, mock_process_batch: MagicMock, tmp_path: Path
    ) -> None:
        """process() returns whatever process_batch returns."""
        fake_config = Config(path=tmp_path)
        mock_make_config.return_value = fake_config
        expected_results = [
            ProcessResult(pdf_path=tmp_path / "a.pdf", success=True, pages_processed=3),
        ]
        mock_process_batch.return_value = expected_results

        result = pdf_goon.process(path=str(tmp_path))

        assert result == expected_results


class TestProcessAcceptsProgressCallback:
    """Verify process() passes progress_callback through to process_batch.

    **Validates: Requirements 9.4**
    """

    @patch("pdf_goon.process_batch")
    @patch("pdf_goon.make_config")
    def test_progress_callback_forwarded_to_process_batch(
        self, mock_make_config: MagicMock, mock_process_batch: MagicMock, tmp_path: Path
    ) -> None:
        """progress_callback kwarg is passed directly to process_batch."""
        fake_config = Config(path=tmp_path)
        mock_make_config.return_value = fake_config
        mock_process_batch.return_value = []

        def my_callback(current: int, total: int, path: Path) -> None:
            pass

        pdf_goon.process(path=str(tmp_path), progress_callback=my_callback)

        mock_process_batch.assert_called_once_with(
            fake_config, progress_callback=my_callback
        )

    @patch("pdf_goon.process_batch")
    @patch("pdf_goon.make_config")
    def test_progress_callback_none_by_default(
        self, mock_make_config: MagicMock, mock_process_batch: MagicMock, tmp_path: Path
    ) -> None:
        """When no progress_callback is provided, None is passed to process_batch."""
        fake_config = Config(path=tmp_path)
        mock_make_config.return_value = fake_config
        mock_process_batch.return_value = []

        pdf_goon.process(path=str(tmp_path))

        mock_process_batch.assert_called_once_with(fake_config, progress_callback=None)
