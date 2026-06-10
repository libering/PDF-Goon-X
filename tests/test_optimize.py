# tests.test_optimize — Tests for pdf_goon.optimize

"""Property-based tests for the optimize module.

Validates correctness properties from the design document:
- Property 4: Optimizer selects correct tool for platform and format
- Property 5: Optimizer failure preserves the original file
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.models import SubprocessError
from pdf_goon.optimize import optimize_image


# Feature: pdf-goon-refactor, Property 4: Optimizer selects correct tool for platform and format
class TestOptimizerToolSelection:
    """Property 4: Optimizer selects correct tool for platform and format.

    For any combination of operating system (nt, posix) and image file extension
    (.png, .jpg, .jpeg), optimize_image SHALL invoke the correct optimization tool:
    pingo on Windows for all formats, oxipng on Linux/macOS for PNG, jpegoptim on
    Linux/macOS for JPEG.

    **Validates: Requirements 8.1**
    """

    @given(
        platform=st.sampled_from(["nt", "posix"]),
        extension=st.sampled_from([".png", ".jpg", ".jpeg"]),
    )
    @settings(max_examples=20)
    def test_correct_tool_invoked_for_platform_and_format(
        self, platform: str, extension: str
    ) -> None:
        """Assert correct tool is invoked for each platform/extension combination."""
        # Record the command that optimize_image passes to run
        recorded_commands: list[list[str]] = []

        def recording_run(cmd: list[str]) -> str:
            recorded_commands.append(cmd)
            return ""

        # Patch get_tool_path to return the bare tool name (avoids
        # cross-platform PosixPath/WindowsPath issues during testing)
        def fake_get_tool_path(name: str) -> str:
            return name

        # Create a real temp file with the given extension
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
            tmp.write(b"fake image content")
            tmp_path = Path(tmp.name)

        try:
            with (
                patch("pdf_goon.optimize.os.name", platform),
                patch("pdf_goon.optimize.get_tool_path", fake_get_tool_path),
            ):
                optimize_image(tmp_path, run=recording_run)

            # Verify a command was recorded
            assert len(recorded_commands) == 1
            cmd = recorded_commands[0]

            # Verify the correct tool is the first element of the command
            if platform == "nt":
                assert cmd[0] == "pingo", (
                    f"Expected pingo on Windows, got: {cmd[0]}"
                )
            elif extension == ".png":
                assert cmd[0] == "oxipng", (
                    f"Expected oxipng for PNG on posix, got: {cmd[0]}"
                )
            else:
                # .jpg or .jpeg
                assert cmd[0] == "jpegoptim", (
                    f"Expected jpegoptim for JPEG on posix, got: {cmd[0]}"
                )
        finally:
            tmp_path.unlink(missing_ok=True)


# Feature: pdf-goon-refactor, Property 5: Optimizer failure preserves the original file
class TestOptimizerFailurePreservesFile:
    """Property 5: Optimizer failure preserves the original file.

    For any image file where the optimization subprocess fails (non-zero exit code),
    optimize_image SHALL leave the original file unmodified and return 0 bytes saved,
    without raising an exception.

    **Validates: Requirements 8.2**
    """

    @given(extension=st.sampled_from([".png", ".jpg", ".jpeg"]))
    @settings(max_examples=20)
    def test_failure_preserves_original_and_returns_zero(
        self, extension: str
    ) -> None:
        """Assert original file is unmodified and return value is 0 on failure."""
        original_content = b"original image content for preservation test"

        def failing_run(cmd: list[str]) -> str:
            raise SubprocessError(
                tool=cmd[0], exit_code=1, stderr="optimization failed"
            )

        # Create a real temp file with known content
        with tempfile.NamedTemporaryFile(
            suffix=extension, delete=False
        ) as tmp:
            tmp.write(original_content)
            tmp_path = Path(tmp.name)

        try:
            result = optimize_image(tmp_path, run=failing_run)

            # Assert return value is 0 (no bytes saved)
            assert result == 0, f"Expected 0 bytes saved on failure, got: {result}"

            # Assert original file content is unchanged
            assert tmp_path.read_bytes() == original_content, (
                "Original file was modified after optimizer failure"
            )
        finally:
            tmp_path.unlink(missing_ok=True)


# --- Unit Tests for optimize_image ---
# Validates: Requirements 8.1, 8.2, 8.3


class TestOptimizeImageBytesSaved:
    """Test bytes-saved calculation when optimization succeeds."""

    def test_returns_bytes_saved_when_file_shrinks(self, tmp_path: Path) -> None:
        """optimize_image returns original_size - new_size when run shrinks the file."""
        image_file = tmp_path / "photo.png"
        original_content = b"A" * 1000
        image_file.write_bytes(original_content)

        def shrinking_run(cmd: list[str]) -> str:
            # Simulate optimizer truncating the file
            image_file.write_bytes(b"A" * 600)
            return ""

        with patch("pdf_goon.optimize.get_tool_path", return_value="oxipng"):
            result = optimize_image(image_file, run=shrinking_run)

        assert result == 400  # 1000 - 600

    def test_returns_zero_for_unsupported_extension(self, tmp_path: Path) -> None:
        """optimize_image returns 0 for unsupported formats like .bmp or .gif."""
        bmp_file = tmp_path / "image.bmp"
        bmp_file.write_bytes(b"BM" + b"\x00" * 100)

        gif_file = tmp_path / "animation.gif"
        gif_file.write_bytes(b"GIF89a" + b"\x00" * 50)

        assert optimize_image(bmp_file) == 0
        assert optimize_image(gif_file) == 0

    def test_returns_zero_when_subprocess_error_raised(self, tmp_path: Path) -> None:
        """optimize_image returns 0 and preserves file when SubprocessError is raised."""
        image_file = tmp_path / "photo.jpg"
        original_content = b"JPEG content here" * 10
        image_file.write_bytes(original_content)

        def failing_run(cmd: list[str]) -> str:
            raise SubprocessError(tool="jpegoptim", exit_code=2, stderr="file corrupt")

        with patch("pdf_goon.optimize.get_tool_path", return_value="jpegoptim"):
            result = optimize_image(image_file, run=failing_run)

        assert result == 0
        assert image_file.read_bytes() == original_content


class TestOptimizeImageToolSelection:
    """Test tool selection logic for each platform/format combination."""

    def test_windows_uses_pingo_for_png(self, tmp_path: Path) -> None:
        """On Windows (os.name='nt'), pingo is used for .png files."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"PNG data")

        recorded: list[list[str]] = []

        def recording_run(cmd: list[str]) -> str:
            recorded.append(cmd)
            return ""

        with (
            patch("pdf_goon.optimize.os.name", "nt"),
            patch("pdf_goon.optimize.get_tool_path", return_value="pingo"),
        ):
            optimize_image(image_file, run=recording_run)

        assert len(recorded) == 1
        assert recorded[0][0] == "pingo"
        assert "-lossless" in recorded[0]

    def test_posix_uses_oxipng_for_png(self, tmp_path: Path) -> None:
        """On posix (os.name='posix'), oxipng is used for .png files."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"PNG data")

        recorded: list[list[str]] = []

        def recording_run(cmd: list[str]) -> str:
            recorded.append(cmd)
            return ""

        with (
            patch("pdf_goon.optimize.os.name", "posix"),
            patch("pdf_goon.optimize.get_tool_path", return_value="oxipng"),
        ):
            optimize_image(image_file, run=recording_run)

        assert len(recorded) == 1
        assert recorded[0][0] == "oxipng"

    def test_posix_uses_jpegoptim_for_jpg(self, tmp_path: Path) -> None:
        """On posix (os.name='posix'), jpegoptim is used for .jpg files."""
        image_file = tmp_path / "photo.jpg"
        image_file.write_bytes(b"JPEG data")

        recorded: list[list[str]] = []

        def recording_run(cmd: list[str]) -> str:
            recorded.append(cmd)
            return ""

        with (
            patch("pdf_goon.optimize.os.name", "posix"),
            patch("pdf_goon.optimize.get_tool_path", return_value="jpegoptim"),
        ):
            optimize_image(image_file, run=recording_run)

        assert len(recorded) == 1
        assert recorded[0][0] == "jpegoptim"
        assert "--strip-all" in recorded[0]
