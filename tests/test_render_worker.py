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


class TestSpecialCharacterPathHandling:
    """Property 5: Special character path handling.

    Validates: Requirements 2.9

    For any valid PDF file path containing spaces, CJK characters, or parentheses,
    when passed as a structured CLI argument to _render_worker.py, the worker SHALL
    correctly resolve and open the file without path quoting errors.

    The key insight: because render_page() uses a list of strings (structured CLI args)
    instead of an f-string inline script, each argument is a separate element — special
    characters are preserved as-is without any quoting/escaping transformations.
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
        """render_page passes paths with special characters as-is in the arg list.

        Validates: Requirements 2.9
        """
        # Why: create the ephemeral output dir inside the test body rather than
        # via the function-scoped `tmp_path` fixture, which Hypothesis rejects
        # because it is not reset between generated examples.
        with tempfile.TemporaryDirectory() as td:
            output_prefix = Path(td) / "output"
            page_info = PageInfo(width_pts=612.0, height_pts=792.0)

            # Capture the command list passed to `run`
            captured_cmds: list[list[str]] = []

            def capturing_run(cmd: list[str]) -> str:
                captured_cmds.append(cmd)
                # Create the expected output file so render_page() doesn't fail
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
            cmd = captured_cmds[0]

            # Verify command structure: [executable, "-m", "pdf_goon._render_worker", path, page, dpi, out]
            assert len(cmd) == 7
            assert cmd[1] == "-m"
            assert cmd[2] == "pdf_goon._render_worker"

            # The pdf_path argument (cmd[3]) is exactly str(pdf_path) — no quoting/escaping
            assert cmd[3] == str(pdf_path)

            # The page_num argument is the string representation
            assert cmd[4] == str(page_num)

            # The dpi argument is the string representation
            assert cmd[5] == str(dpi)

        # The output path (cmd[6]) ends with .png and is a valid path string
        assert cmd[6].endswith(".png")
