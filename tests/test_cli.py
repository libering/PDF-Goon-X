# tests.test_cli — Tests for pdf_goon.cli

"""Unit tests for CLI argument parsing, exit codes, and banner output."""

from unittest.mock import patch

import pytest

from pdf_goon.cli import _build_parser, main
from pdf_goon.models import PdfGoonError, VERSION


# --- Argument Parsing Tests ---


class TestArgumentDefaults:
    """Test default argument values match v1.0.1."""

    def test_default_values(self):
        parser = _build_parser()
        args = parser.parse_args([])

        assert args.path == "."
        assert args.verbose is False
        assert args.replace is False
        assert args.include_subdirectories is False
        assert args.dpi_text == 400
        assert args.min_w == 500
        assert args.optimize is True
        assert args.debug is False
        assert args.force_render is False


class TestArgumentFlags:
    """Test individual CLI flags set correct values."""

    def test_verbose_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-v"])
        assert args.verbose is True

    def test_replace_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-r"])
        assert args.replace is True

    def test_recursive_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["-recursive"])
        assert args.include_subdirectories is True

    def test_dpi_text_custom(self):
        parser = _build_parser()
        args = parser.parse_args(["-dpi-text", "300"])
        assert args.dpi_text == 300

    def test_min_w_custom(self):
        parser = _build_parser()
        args = parser.parse_args(["-min-w", "800"])
        assert args.min_w == 800

    def test_no_optimization_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--no-optimization"])
        assert args.optimize is False

    def test_debug_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--debug"])
        assert args.debug is True


# --- Exit Code Tests ---


class TestExitCodes:
    """Test exit codes for success, PdfGoonError, and unexpected error."""

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", return_value=[])
    def test_exit_code_0_on_success(self, mock_process):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", side_effect=PdfGoonError("test error"))
    def test_exit_code_1_on_pdf_goon_error(self, mock_process):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", side_effect=RuntimeError("unexpected"))
    def test_exit_code_2_on_unexpected_error(self, mock_process):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2


# --- Banner Tests ---


class TestBanner:
    """Test banner output contains version string."""

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", return_value=[])
    def test_banner_contains_version(self, mock_process, capsys):
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert f"PDF-Goon v{VERSION}" in captured.out
