# tests.test_extract — Tests for pdf_goon.extract

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest.mock as mock

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from pdf_goon.extract import extract_images, render_page
from pdf_goon.models import PageInfo, PdfGoonError, SubprocessError


class TestExtractImages:
    """Tests for extract_images using pypdf."""

    def test_extracts_jpeg_images(self, tmp_path: Path) -> None:
        """extract_images writes raw JPEG data directly."""
        with mock.patch("pypdf.PdfReader") as mock_reader:
            mock_img = mock.MagicMock()
            mock_img.name = "image.jpg"
            mock_img.data = b"\xff\xd8\xff\xe0fake_jpeg_data"

            mock_page = mock.MagicMock()
            mock_page.images = [mock_img]
            mock_reader.return_value.pages = [mock_page]

            pdf_path = tmp_path / "input.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 dummy")
            output_prefix = tmp_path / "page"
            result = extract_images(pdf_path, page_num=1, output_prefix=output_prefix)

            assert len(result) == 1
            assert result[0].suffix == ".jpg"
            assert result[0].read_bytes() == b"\xff\xd8\xff\xe0fake_jpeg_data"

    def test_extracts_png_images_via_pil(self, tmp_path: Path) -> None:
        """extract_images saves PNGs using PIL to ensure valid format."""
        with mock.patch("pypdf.PdfReader") as mock_reader:
            mock_img = mock.MagicMock()
            mock_img.name = "image.png"
            # .image is a PIL Image mock
            mock_pil = mock.MagicMock()
            mock_img.image = mock_pil

            mock_page = mock.MagicMock()
            mock_page.images = [mock_img]
            mock_reader.return_value.pages = [mock_page]

            pdf_path = tmp_path / "input.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 dummy")
            output_prefix = tmp_path / "page"
            result = extract_images(pdf_path, page_num=1, output_prefix=output_prefix)

            assert len(result) == 1
            assert result[0].suffix == ".png"
            mock_pil.save.assert_called_once()

    def test_extracts_multiple_images(self, tmp_path: Path) -> None:
        """extract_images handles multiple images on one page."""
        with mock.patch("pypdf.PdfReader") as mock_reader:
            imgs = []
            for i in range(3):
                m = mock.MagicMock()
                m.name = f"img{i}.jpg"
                m.data = f"data{i}".encode()
                imgs.append(m)

            mock_page = mock.MagicMock()
            mock_page.images = imgs
            mock_reader.return_value.pages = [mock_page]

            pdf_path = tmp_path / "input.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 dummy")
            output_prefix = tmp_path / "page"
            result = extract_images(pdf_path, page_num=1, output_prefix=output_prefix)

            assert len(result) == 3
            names = sorted(p.name for p in result)
            assert names == ["page-000.jpg", "page-001.jpg", "page-002.jpg"]

    def test_raises_on_failure(self, tmp_path: Path) -> None:
        """extract_images wraps exceptions in PdfGoonError."""
        pdf_path = tmp_path / "x.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 dummy")
        with mock.patch("pypdf.PdfReader", side_effect=Exception("bad")):
            with pytest.raises(PdfGoonError, match="Failed to extract"):
                extract_images(pdf_path, 1, tmp_path / "out")


class TestRenderPage:
    """Tests for render_page using pypdfium2 subprocess isolation."""

    def test_renders_page_returns_output_path(self, tmp_path: Path) -> None:
        """render_page returns the expected .png output path."""
        pdf_path = tmp_path / "input.pdf"
        pdf_path.write_bytes(b"dummy pdf content")
        output_prefix = tmp_path / "rendered"
        page_info = PageInfo(width_pts=612.0, height_pts=792.0)

        def fake_run(cmd: list[str]) -> str:
            # Simulate the subprocess creating the output file
            out_file = output_prefix.with_suffix(".png")
            out_file.write_bytes(b"fake png")
            return ""

        result = render_page(
            pdf_path,
            page_num=1,
            output_prefix=output_prefix,
            dpi=150.0,
            page_info=page_info,
            run=fake_run,
        )

        expected_out = tmp_path / "rendered.png"
        assert result == [expected_out]

    def test_raises_pdfgoonerror_on_failure(self, tmp_path: Path) -> None:
        """render_page wraps SubprocessError in PdfGoonError."""
        pdf_path = tmp_path / "input.pdf"
        pdf_path.write_bytes(b"dummy pdf content")

        def failing_run(cmd: list[str]) -> str:
            raise SubprocessError(tool="python", exit_code=1, stderr="Pdfium crashed")

        with pytest.raises(PdfGoonError, match="Failed to render page 1"):
            render_page(
                pdf_path,
                page_num=1,
                output_prefix=tmp_path / "out",
                dpi=72.0,
                page_info=PageInfo(width_pts=612.0, height_pts=792.0),
                run=failing_run,
            )


# Feature: codebase-improvements, Property 4: Worker error propagation (caller side)
# **Validates: Requirements 2.7**


@settings(max_examples=100)
@given(
    stderr_msg=st.text(min_size=1, max_size=200),
    page_num=st.integers(min_value=1, max_value=9999),
    tool_name=st.text(min_size=1, max_size=50),
)
def test_worker_error_propagation_caller(
    stderr_msg: str, page_num: int, tool_name: str
) -> None:
    """render_page wraps any SubprocessError into PdfGoonError preserving stderr and cause chain.

    For any SubprocessError raised by the injected run callable, render_page SHALL
    raise PdfGoonError whose message contains the stderr content, with the original
    SubprocessError chained as __cause__.
    """
    # Use a context-managed temp dir instead of the function-scoped tmp_path
    # fixture: hypothesis reruns this body per generated example and does not
    # reset function-scoped fixtures, which trips FailedHealthCheck.
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        pdf_path = tmp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 dummy")

        def failing_run(cmd: list[str]) -> str:
            raise SubprocessError(tool=tool_name, exit_code=1, stderr=stderr_msg)

        with pytest.raises(PdfGoonError) as exc_info:
            render_page(
                pdf_path,
                page_num=page_num,
                output_prefix=tmp_dir / "out",
                dpi=72.0,
                page_info=PageInfo(width_pts=612.0, height_pts=792.0),
                run=failing_run,
            )

        # Stderr content must appear in the wrapped error message
        assert stderr_msg in str(exc_info.value)
        # Exception chaining preserves original cause for debugging
        assert isinstance(exc_info.value.__cause__, SubprocessError)
        assert exc_info.value.__cause__.stderr == stderr_msg
        assert exc_info.value.__cause__.tool == tool_name


# Feature: codebase-improvements, Property 2: Render command construction
# **Validates: Requirements 2.2**


@st.composite
def valid_render_inputs(draw: st.DrawFn) -> tuple[Path, int, float, Path]:
    """Generate valid inputs for render_page(): pdf_path, page_num, dpi, output_prefix.

    Constrains paths to safe ASCII filenames and reasonable numeric ranges
    to focus on command construction logic rather than filesystem edge cases.
    """
    # Safe filename characters — avoids filesystem issues unrelated to command construction
    filename = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"), whitelist_characters="_-"
            ),
            min_size=1,
            max_size=30,
        )
    )
    pdf_name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"), whitelist_characters="_-"
            ),
            min_size=1,
            max_size=30,
        )
    )
    page_num = draw(st.integers(min_value=1, max_value=9999))
    dpi = draw(
        st.floats(
            min_value=36.0, max_value=2400.0, allow_nan=False, allow_infinity=False
        )
    )

    # Synthetic paths — filesystem not touched since we inject a fake run callable
    pdf_path = Path(f"C:/tmp/{pdf_name}.pdf")
    output_prefix = Path(f"C:/tmp/output/{filename}")

    return pdf_path, page_num, dpi, output_prefix


class TestRenderCommandConstruction:
    """Property test: render_page() constructs the correct command list."""

    @given(data=valid_render_inputs())
    @settings(max_examples=100)
    def test_command_structure_matches_spec(
        self,
        data: tuple[Path, int, float, Path],
    ) -> None:
        """render_page() SHALL construct a command of the form:
        [sys.executable, "-m", "pdf_goon._render_worker",
         str(pdf_path), str(page_num), str(dpi), str(output_path)]
        and pass it to the `run` callable.
        """
        pdf_path, page_num, dpi, output_prefix = data

        # Capture the command passed to the run callable
        captured_cmds: list[list[str]] = []

        def capturing_run(cmd: list[str]) -> str:
            """Fake run: captures command, creates expected output file."""
            captured_cmds.append(cmd)
            # render_page expects the output file to exist after run completes
            out_file = output_prefix.with_suffix(".png")
            if out_file.name == output_prefix.name:
                out_file = output_prefix.parent / f"{output_prefix.name}.png"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(b"fake png")
            return ""

        page_info = PageInfo(width_pts=612.0, height_pts=792.0)

        render_page(
            pdf_path,
            page_num=page_num,
            output_prefix=output_prefix,
            dpi=dpi,
            page_info=page_info,
            run=capturing_run,
        )

        # Exactly one command must have been issued
        assert len(captured_cmds) == 1
        cmd = captured_cmds[0]

        # Compute expected output path (mirrors render_page's logic)
        expected_out = output_prefix.with_suffix(".png")
        if expected_out.name == output_prefix.name:
            expected_out = output_prefix.parent / f"{output_prefix.name}.png"

        # Verify command structure per design spec (Requirement 2.2)
        assert cmd[0] == sys.executable
        assert cmd[1] == "-m"
        assert cmd[2] == "pdf_goon._render_worker"
        assert cmd[3] == str(pdf_path)
        assert cmd[4] == str(page_num)
        assert cmd[5] == str(dpi)
        assert cmd[6] == str(expected_out)
        assert len(cmd) == 7
