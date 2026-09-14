# tests.test_tools — Tests for pdf_goon.tools
# Feature: pdf-goon-refactor, Property 10: Subprocess failure exceptions contain diagnostic info

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.models import SubprocessError
from pdf_goon.tools import get_tool_path, run_command


@given(
    tool_name=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    exit_code=st.integers(min_value=1, max_value=255),
    stderr=st.text(min_size=0, max_size=200),
)
@settings(max_examples=100)
def test_subprocess_error_contains_diagnostic_info(
    tool_name: str, exit_code: int, stderr: str
) -> None:
    """Property 10: For any non-zero exit code, SubprocessError stores the tool name,
    exit code, and stderr as accessible attributes, and includes the tool name and
    exit code in its string representation.

    Validates: Requirements 5.1
    """
    err = SubprocessError(tool=tool_name, exit_code=exit_code, stderr=stderr)

    # Attributes are stored correctly
    assert err.tool == tool_name
    assert err.exit_code == exit_code
    assert err.stderr == stderr

    # String representation contains diagnostic info
    message = str(err)
    assert tool_name in message
    assert str(exit_code) in message


# --- Unit Tests for tools.py ---
# Task 3.3: Test get_tool_path, run_command, check_poppler_available


class TestGetToolPath:
    """Tests for get_tool_path resolution order: MEIPASS → local (allowlist) → PATH → bare name."""

    def test_non_allowlisted_tool_skips_local_directory(self, tmp_path: Path) -> None:
        """A tool name NOT in the allowlist is never resolved from the local directory."""
        # Create a file with the tool name in the package directory
        # Even though it exists locally, it should be skipped
        with (
            patch("pdf_goon.tools.sys") as mock_sys,
            patch("pdf_goon.tools.shutil.which", return_value=None),
        ):
            del mock_sys._MEIPASS
            # Patch Path(__file__).parent / tool_name to "exist"
            # but the tool name is not in the allowlist
            with patch("pdf_goon.tools.Path.exists", return_value=True):
                result = get_tool_path("evil_binary")

        # Should NOT return a local path — should fall through to bare name
        assert result == "evil_binary"

    def test_allowlisted_tool_resolves_from_local_directory(
        self, tmp_path: Path
    ) -> None:
        """A tool name IN the allowlist CAN be resolved from the local directory."""
        with (
            patch("pdf_goon.tools.sys") as mock_sys,
            patch("pdf_goon.tools.shutil.which", return_value=None),
        ):
            del mock_sys._MEIPASS
            with patch("pdf_goon.tools.Path.exists", return_value=True):
                result = get_tool_path("pingo")

        # Should resolve from local (Path.exists returns True)
        assert "pingo" in result
        assert result != "pingo"  # Not the bare name — it's a full path

    def test_resolves_from_meipass_when_bundled(self, tmp_path: Path) -> None:
        """get_tool_path returns bundled path when sys._MEIPASS is set and tool exists."""
        tool_file = tmp_path / "pdfimages"
        tool_file.touch()

        with patch("pdf_goon.tools.sys") as mock_sys:
            mock_sys._MEIPASS = str(tmp_path)
            # hasattr check needs the attribute to exist
            result = get_tool_path("pdfimages")

        assert result == str(tool_file)

    def test_falls_back_to_path_when_no_local_or_bundled(self) -> None:
        """get_tool_path uses shutil.which when no bundled or local file exists."""
        with (
            patch("pdf_goon.tools.sys") as mock_sys,
            patch("pdf_goon.tools.shutil.which", return_value="/usr/bin/pdfimages"),
        ):
            # Remove _MEIPASS so bundled path is skipped
            del mock_sys._MEIPASS
            # Patch Path.exists to return False for local file check
            with patch("pdf_goon.tools.Path.exists", return_value=False):
                result = get_tool_path("pdfimages")

        assert result == "/usr/bin/pdfimages"

    def test_returns_bare_name_when_nothing_found(self) -> None:
        """get_tool_path returns the bare tool name as last resort."""
        with (
            patch("pdf_goon.tools.sys") as mock_sys,
            patch("pdf_goon.tools.shutil.which", return_value=None),
        ):
            del mock_sys._MEIPASS
            with patch("pdf_goon.tools.Path.exists", return_value=False):
                result = get_tool_path("pdfimages")

        assert result == "pdfimages"


class TestRunCommand:
    """Tests for run_command subprocess execution and error handling."""

    def test_returns_stdout_on_success(self) -> None:
        """run_command returns stdout when subprocess exits with code 0."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "page count: 5\n"
        mock_result.stderr = ""

        with patch("pdf_goon.tools.subprocess.run", return_value=mock_result):
            output = run_command(["pdfinfo", "test.pdf"])

        assert output == "page count: 5\n"

    def test_raises_subprocess_error_on_nonzero_exit(self) -> None:
        """run_command raises SubprocessError when subprocess exits with non-zero code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: file not found"

        with patch("pdf_goon.tools.subprocess.run", return_value=mock_result):
            with pytest.raises(SubprocessError) as exc_info:
                run_command(["pdfinfo", "missing.pdf"])

        assert exc_info.value.tool == "pdfinfo"
        assert exc_info.value.exit_code == 1
        assert "file not found" in exc_info.value.stderr

    def test_raises_subprocess_error_on_timeout(self) -> None:
        """run_command raises SubprocessError with timeout info when process hangs."""
        with patch(
            "pdf_goon.tools.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["pdfinfo", "huge.pdf"], timeout=300
            ),
        ):
            with pytest.raises(SubprocessError) as exc_info:
                run_command(["pdfinfo", "huge.pdf"])

        assert exc_info.value.tool == "pdfinfo"
        assert exc_info.value.exit_code == -1
        assert "timed out" in exc_info.value.stderr.lower()
