# tests.test_integration — Integration tests comparing refactored output to v1.0.1 behavior

"""Integration tests verifying backward compatibility with PDF-Goon v1.0.1.

Tests cover:
- CLI argument compatibility (all flags accepted with same defaults)
- Output filename format matches v1.0.1 (e.g., 001.png, 002_r.png)
- Exit code behavior matches v1.0.1
- Configuration summary output format

Requirements: 12.1, 12.2, 12.3
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from pdf_goon.cli import _build_parser, main
from pdf_goon.core import _finalize_page_files
from pdf_goon.models import Config, PdfGoonError, VERSION


# --- CLI Argument Compatibility ---


class TestCLIArgumentCompatibility:
    """Verify all v1.0.1 CLI flags are accepted with the same defaults."""

    def test_all_v1_flags_accepted(self):
        """Parser accepts every flag from v1.0.1 without error."""
        parser = _build_parser()
        # All flags combined
        args = parser.parse_args([
            "/some/path",
            "-v",
            "-r",
            "-recursive",
            "-dpi-text", "600",
            "-min-w", "300",
            "--no-optimization",
            "--debug",
            "--force-render",
        ])
        assert args.path == "/some/path"
        assert args.verbose is True
        assert args.replace is True
        assert args.include_subdirectories is True
        assert args.dpi_text == 600
        assert args.min_w == 300
        assert args.optimize is False
        assert args.debug is True
        assert args.force_render is True

    def test_defaults_match_v1(self):
        """Default namespace values match v1.0.1 exactly."""
        parser = _build_parser()
        args = parser.parse_args([])

        # v1.0.1 defaults
        assert args.path == "."
        assert args.verbose is False
        assert args.replace is False
        assert args.include_subdirectories is False
        assert args.dpi_text == 400
        assert args.min_w == 500
        assert args.optimize is True
        assert args.debug is False
        assert args.force_render is False

    def test_long_form_verbose(self):
        """--verbose long form works like v1.0.1."""
        parser = _build_parser()
        args = parser.parse_args(["--verbose"])
        assert args.verbose is True

    def test_long_form_replace(self):
        """--replace long form works like v1.0.1."""
        parser = _build_parser()
        args = parser.parse_args(["--replace"])
        assert args.replace is True

    def test_include_subdirectories_long_form(self):
        """--include-subdirectories long form works like v1.0.1."""
        parser = _build_parser()
        args = parser.parse_args(["--include-subdirectories"])
        assert args.include_subdirectories is True

    def test_positional_path_argument(self):
        """Positional path argument works like v1.0.1."""
        parser = _build_parser()
        args = parser.parse_args(["/my/pdfs"])
        assert args.path == "/my/pdfs"


# --- Output Filename Format ---


class TestOutputFilenameFormat:
    """Verify output filenames match v1.0.1 naming pattern."""

    def test_extracted_page_naming(self, tmp_path: Path):
        """Extracted page 1 → '001.png'."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Simulate pdfimages output: page_1_tmp-000.png
        workspace_file = tmp_path / "page_1_tmp-000.png"
        workspace_file.write_bytes(b"fake png data")

        config = Config(path=tmp_path, optimize=False)
        _finalize_page_files(
            generated_files=[workspace_file],
            mask_indices=[],
            was_rendered=False,
            page=1,
            output_dir=output_dir,
            config=config,
        )

        result_files = list(output_dir.iterdir())
        assert len(result_files) == 1
        assert result_files[0].name == "001.png"

    def test_rendered_page_naming(self, tmp_path: Path):
        """Rendered page 2 → '002_r.png'."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Simulate pdftocairo output: page_2_tmp-2.png
        workspace_file = tmp_path / "page_2_tmp-2.png"
        workspace_file.write_bytes(b"fake png data")

        config = Config(path=tmp_path, optimize=False)
        _finalize_page_files(
            generated_files=[workspace_file],
            mask_indices=[],
            was_rendered=True,
            page=2,
            output_dir=output_dir,
            config=config,
        )

        result_files = list(output_dir.iterdir())
        assert len(result_files) == 1
        assert result_files[0].name == "002_r.png"

    def test_multiple_images_same_page(self, tmp_path: Path):
        """Multiple images on page 1 → '001.png', '001_001.png'."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Simulate pdfimages output with multiple images on same page
        file_0 = tmp_path / "page_1_tmp-000.png"
        file_1 = tmp_path / "page_1_tmp-001.png"
        file_0.write_bytes(b"image 0")
        file_1.write_bytes(b"image 1")

        config = Config(path=tmp_path, optimize=False)
        _finalize_page_files(
            generated_files=[file_0, file_1],
            mask_indices=[],
            was_rendered=False,
            page=1,
            output_dir=output_dir,
            config=config,
        )

        result_files = sorted(f.name for f in output_dir.iterdir())
        assert "001.png" in result_files
        assert "001_001.png" in result_files

    def test_jpeg_extension_preserved(self, tmp_path: Path):
        """JPEG files keep their extension: '001.jpg'."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        workspace_file = tmp_path / "page_1_tmp-000.jpg"
        workspace_file.write_bytes(b"fake jpg data")

        config = Config(path=tmp_path, optimize=False)
        _finalize_page_files(
            generated_files=[workspace_file],
            mask_indices=[],
            was_rendered=False,
            page=1,
            output_dir=output_dir,
            config=config,
        )

        result_files = list(output_dir.iterdir())
        assert len(result_files) == 1
        assert result_files[0].name == "001.jpg"

    def test_rendered_jpeg_naming(self, tmp_path: Path):
        """Rendered JPEG page 3 → '003_r.jpg'."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        workspace_file = tmp_path / "page_3_tmp-3.jpg"
        workspace_file.write_bytes(b"fake jpg data")

        config = Config(path=tmp_path, optimize=False)
        _finalize_page_files(
            generated_files=[workspace_file],
            mask_indices=[],
            was_rendered=True,
            page=3,
            output_dir=output_dir,
            config=config,
        )

        result_files = list(output_dir.iterdir())
        assert len(result_files) == 1
        assert result_files[0].name == "003_r.jpg"

    def test_mask_files_excluded(self, tmp_path: Path):
        """Mask files are deleted, not moved to output."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Image file and mask file
        img_file = tmp_path / "page_1_tmp-000.png"
        mask_file = tmp_path / "page_1_tmp-001.png"
        img_file.write_bytes(b"real image")
        mask_file.write_bytes(b"mask data")

        config = Config(path=tmp_path, optimize=False)
        _finalize_page_files(
            generated_files=[img_file, mask_file],
            mask_indices=["001"],
            was_rendered=False,
            page=1,
            output_dir=output_dir,
            config=config,
        )

        result_files = list(output_dir.iterdir())
        assert len(result_files) == 1
        assert result_files[0].name == "001.png"
        # Mask file should be deleted
        assert not mask_file.exists()

    def test_page_number_zero_padded_to_three_digits(self, tmp_path: Path):
        """Page numbers are zero-padded to 3 digits like v1.0.1."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        workspace_file = tmp_path / "page_99_tmp-000.png"
        workspace_file.write_bytes(b"fake png data")

        config = Config(path=tmp_path, optimize=False)
        _finalize_page_files(
            generated_files=[workspace_file],
            mask_indices=[],
            was_rendered=False,
            page=99,
            output_dir=output_dir,
            config=config,
        )

        result_files = list(output_dir.iterdir())
        assert len(result_files) == 1
        assert result_files[0].name == "099.png"


# --- Exit Code Behavior ---


class TestExitCodeBehavior:
    """Verify exit codes match v1.0.1 behavior."""

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", return_value=[])
    def test_exit_0_on_success(self, mock_process):
        """Successful processing exits with code 0."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", side_effect=PdfGoonError("missing tools"))
    def test_exit_1_on_pdf_goon_error(self, mock_process):
        """PdfGoonError (e.g., missing Poppler) exits with code 1."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", side_effect=RuntimeError("crash"))
    def test_exit_2_on_unexpected_error(self, mock_process):
        """Unexpected exceptions exit with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2


# --- Configuration Summary Output Format ---


class TestConfigurationSummaryFormat:
    """Verify configuration summary output matches v1.0.1 format."""

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", return_value=[])
    def test_config_summary_contains_all_fields(self, mock_process, capsys):
        """Configuration summary includes Path, Recursive, Replace, DPI, Min-Width, Optimization."""
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()

        # v1.0.1 format:
        # Configuration => Path: '.' | Recursive (include subdirectories): False
        # | Replace: False | DPI for Textpages: 400 | Min-Width: 500px
        # | Lossless Optimization: True
        assert "Configuration =>" in captured.out
        assert "Path: '.'" in captured.out
        assert "Recursive (include subdirectories): False" in captured.out
        assert "Replace: False" in captured.out
        assert "DPI for Textpages: 400" in captured.out
        assert "Min-Width: 500px" in captured.out
        assert "Lossless Optimization: True" in captured.out

    @patch("sys.argv", ["pdf-goon", "/custom/path", "-r", "-recursive", "-dpi-text", "300", "-min-w", "800", "--no-optimization"])
    @patch("pdf_goon.cli.pdf_goon.process", return_value=[])
    def test_config_summary_reflects_custom_args(self, mock_process, capsys):
        """Configuration summary reflects non-default argument values."""
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()

        assert "Path: '/custom/path'" in captured.out
        assert "Recursive (include subdirectories): True" in captured.out
        assert "Replace: True" in captured.out
        assert "DPI for Textpages: 300" in captured.out
        assert "Min-Width: 800px" in captured.out
        assert "Lossless Optimization: False" in captured.out

    @patch("sys.argv", ["pdf-goon"])
    @patch("pdf_goon.cli.pdf_goon.process", return_value=[])
    def test_banner_format_matches_v1(self, mock_process, capsys):
        """Banner output matches v1.0.1 format with separator lines."""
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()

        lines = captured.out.splitlines()
        # v1.0.1 banner: separator, version, description, separator
        assert lines[0] == "=" * 60
        assert f"PDF-Goon v{VERSION}" in lines[1]
        # Description line
        assert "PDF ripping tool" in captured.out
        # Separator after config
        assert captured.out.count("=" * 60) >= 2
