# tests.test_render_worker — Property tests for pdf_goon._render_worker
# Feature: codebase-improvements, Property 3: Worker error propagation (worker side)

from __future__ import annotations

import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon._render_worker import main
from pdf_goon.extract import render_page
from pdf_goon.models import PageInfo


# --- Hypothesis strategies ---

# Generate argument lists that do NOT have exactly 5 elements (wrong arg count).
# Why: worker expects exactly 5 argv elements (script + 4 args); any other count
# must trigger an error exit.
wrong_arg_count_argv = st.lists(
    st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    min_size=1,
    max_size=10,
).filter(lambda xs: len(xs) != 5)

# Strings that cannot be parsed as int (for page_num argument).
non_int_strings = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L", "P", "Z")),
).filter(lambda s: not s.strip().lstrip("-").isdigit())

# Strings that cannot be parsed as float (for dpi argument).
non_float_strings = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=("L", "P", "Z")),
).filter(lambda s: _is_not_float(s))


def _is_not_float(s: str) -> bool:
    """Return True if string cannot be parsed as a float."""
    try:
        float(s)
        return False
    except (ValueError, OverflowError):
        return True


# --- Property tests ---


@given(argv=wrong_arg_count_argv)
@settings(max_examples=100)
def test_worker_error_propagation_wrong_arg_count(argv: list[str]) -> None:
    """Property 3: For any wrong argument count (not exactly 5), the worker
    SHALL exit with code 1 and write a non-empty message to stderr.

    Validates: Requirements 2.6
    """
    stderr_capture = StringIO()

    with (
        patch.object(sys, "argv", argv),
        patch("sys.stderr", stderr_capture),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert len(stderr_capture.getvalue()) > 0


@given(
    pdf_path=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    page_num=non_int_strings,
    dpi=st.text(min_size=1, max_size=10),
    output_path=st.text(min_size=1, max_size=30),
)
@settings(max_examples=100)
def test_worker_error_propagation_invalid_page_num(
    pdf_path: str, page_num: str, dpi: str, output_path: str
) -> None:
    """Property 3: For any invalid page_num string that cannot be parsed as int,
    the worker SHALL exit with code 1 and write a non-empty message to stderr.

    Validates: Requirements 2.6
    """
    argv = ["_render_worker", pdf_path, page_num, dpi, output_path]
    stderr_capture = StringIO()

    with (
        patch.object(sys, "argv", argv),
        patch("sys.stderr", stderr_capture),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert len(stderr_capture.getvalue()) > 0


@given(
    pdf_path=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    page_num=st.integers(min_value=1, max_value=999).map(str),
    dpi=non_float_strings,
    output_path=st.text(min_size=1, max_size=30),
)
@settings(max_examples=100)
def test_worker_error_propagation_invalid_dpi(
    pdf_path: str, page_num: str, dpi: str, output_path: str
) -> None:
    """Property 3: For any invalid dpi string that cannot be parsed as float,
    the worker SHALL exit with code 1 and write a non-empty message to stderr.

    Validates: Requirements 2.6
    """
    argv = ["_render_worker", pdf_path, page_num, dpi, output_path]
    stderr_capture = StringIO()

    with (
        patch.object(sys, "argv", argv),
        patch("sys.stderr", stderr_capture),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert len(stderr_capture.getvalue()) > 0


@given(
    page_num=st.integers(min_value=1, max_value=999).map(str),
    dpi=st.floats(
        min_value=1.0, max_value=1200.0, allow_nan=False, allow_infinity=False
    ).map(str),
    output_path=st.text(min_size=1, max_size=30),
)
@settings(max_examples=100)
def test_worker_error_propagation_nonexistent_pdf(
    page_num: str, dpi: str, output_path: str
) -> None:
    """Property 3: For any non-existent PDF path with valid page_num/dpi args,
    the worker SHALL exit with code 1 and write a non-empty message to stderr.

    Validates: Requirements 2.6
    """
    # Why: use a temp dir to guarantee the path does not exist on disk
    with tempfile.TemporaryDirectory() as tmp_dir:
        nonexistent_pdf = str(Path(tmp_dir) / "nonexistent_abc123.pdf")
        argv = ["_render_worker", nonexistent_pdf, page_num, dpi, output_path]
        stderr_capture = StringIO()

        with (
            patch.object(sys, "argv", argv),
            patch("sys.stderr", stderr_capture),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        assert len(stderr_capture.getvalue()) > 0


# --- Property 5: Special character path handling ---
# Feature: codebase-improvements, Property 5: Special character path handling

# Characters that historically cause quoting issues in shell commands:
# spaces, CJK (Chinese/Japanese/Korean), parentheses, brackets, accented chars
_SPECIAL_CHAR_ALPHABET = st.sampled_from(
    list("abcdef0123 中文日本語テスト()") + list("[]données café Ångström")
)

# Generate directory names with special characters
_special_dir_names = st.text(
    alphabet=_SPECIAL_CHAR_ALPHABET,
    min_size=1,
    max_size=30,
).filter(
    # Exclude names that are only whitespace (invalid as path components)
    lambda s: s.strip() != ""
)


@st.composite
def special_char_pdf_paths(draw: st.DrawFn) -> Path:
    """Generate PDF file paths with special characters in directory and filename."""
    dir_name = draw(_special_dir_names)
    stem = draw(_special_dir_names)
    return Path(f"C:/tmp/{dir_name}/{stem}.pdf")


def _assert_special_char_cmd(
    cmd: list[str],
    pdf_path: Path,
    page_num: int,
    dpi: float,
) -> None:
    """Assert structured CLI command preserves special characters."""
    assert len(cmd) == 7
    assert cmd[1] == "-m"
    assert cmd[2] == "pdf_goon._render_worker"
    assert cmd[3] == str(pdf_path)
    assert cmd[4] == str(page_num)
    assert cmd[5] == str(dpi)
    assert cmd[6].endswith(".png")


class TestSpecialCharacterPathHandling:
    """Property 5: Special character path handling.

    Validates: Requirements 2.9
    """

    @settings(max_examples=100)
    @given(
        pdf_path=special_char_pdf_paths(),
        page_num=st.integers(min_value=1, max_value=9999),
        dpi=st.floats(
            min_value=36.0, max_value=2400.0, allow_nan=False, allow_infinity=False
        ),
    )
    def test_special_char_paths_preserved_in_command_args(
        self,
        pdf_path: Path,
        page_num: int,
        dpi: float,
    ) -> None:
        """render_page passes paths with special characters as-is in the arg list."""
        with tempfile.TemporaryDirectory() as td:
            output_prefix = Path(td) / "output"
            page_info = PageInfo(width_pts=612.0, height_pts=792.0)
            captured_cmds: list[list[str]] = []

            def capturing_run(cmd: list[str]) -> str:
                captured_cmds.append(cmd)
                out_file = Path(cmd[-1])
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_bytes(b"\x89PNG fake")
                return ""

            render_page(
                pdf_path,
                page_num=page_num,
                output_prefix=output_prefix,
                dpi=dpi,
                page_info=page_info,
                run=capturing_run,
            )

            assert len(captured_cmds) == 1
            _assert_special_char_cmd(captured_cmds[0], pdf_path, page_num, dpi)


# ---------------------------------------------------------------------------
# Tests for memory lifecycle and color normalization in _render_worker
# ---------------------------------------------------------------------------


def test_normalize_rendered_image_rgb_grayscale_converts_to_l() -> None:
    from PIL import Image
    from pdf_goon._render_worker import _normalize_rendered_image

    img = Image.new("RGB", (100, 100), (128, 128, 128))
    norm = _normalize_rendered_image(img)
    assert norm.mode == "L"
    assert norm.size == (100, 100)
    assert norm.getpixel((50, 50)) == 128


def test_normalize_rendered_image_rgb_color_retains_rgb() -> None:
    from PIL import Image
    from pdf_goon._render_worker import _normalize_rendered_image

    img = Image.new("RGB", (100, 100), (200, 128, 100))
    norm = _normalize_rendered_image(img)
    assert norm.mode == "RGB"
    assert norm.size == (100, 100)
    assert norm.getpixel((50, 50)) == (200, 128, 100)


def test_normalize_rendered_image_rgba_grayscale_converts_to_la() -> None:
    from PIL import Image
    from pdf_goon._render_worker import _normalize_rendered_image

    img = Image.new("RGBA", (100, 100), (80, 80, 80, 255))
    norm = _normalize_rendered_image(img)
    assert norm.mode == "LA"
    assert norm.size == (100, 100)


def test_render_single_page_frees_memory_and_closes_handles(tmp_path: Path) -> None:
    from unittest.mock import MagicMock
    from PIL import Image
    from pdf_goon._render_worker import _render_single_page_to_file

    mock_pdf = MagicMock()
    mock_page = MagicMock()
    mock_bitmap = MagicMock()
    mock_pdf.__getitem__.return_value = mock_page
    mock_page.render.return_value = mock_bitmap
    real_pil = Image.new("RGB", (10, 10), (255, 255, 255))
    mock_bitmap.to_pil.return_value = real_pil

    out_file = tmp_path / "rendered.png"
    _render_single_page_to_file(mock_pdf, 1, 150.0, out_file)

    assert out_file.exists()
    assert mock_page.close.called
    assert mock_bitmap.close.called

