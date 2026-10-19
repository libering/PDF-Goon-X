"""Architecture and code constraint tests.

Enforces across ALL modules in pdf_goon with ZERO EXEMPTION:
1. Single file length <= 500 lines across the entire codebase.
2. Single function length <= 50 lines across the entire codebase.
"""

from __future__ import annotations

import ast
import pathlib

MAX_FILE_LINES = 500
MAX_FUNC_LINES = 50

PKG_DIR = pathlib.Path(__file__).resolve().parent.parent / "pdf_goon"


def test_all_files_line_limits() -> None:
    """Verify NO python source file anywhere in pdf_goon exceeds MAX_FILE_LINES (500 lines)."""
    violations = []
    for py_file in PKG_DIR.rglob("*.py"):
        lines = py_file.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_FILE_LINES:
            violations.append(
                f"{py_file.relative_to(PKG_DIR)} has {len(lines)} lines (exceeds {MAX_FILE_LINES})"
            )

    assert not violations, "File line limit violations:\n" + "\n".join(violations)


def test_all_functions_line_limits() -> None:
    """Verify NO function or method anywhere in pdf_goon exceeds MAX_FUNC_LINES (50 lines)."""
    violations = []
    for py_file in PKG_DIR.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_len = (node.end_lineno or 0) - node.lineno + 1
                if func_len > MAX_FUNC_LINES:
                    violations.append(
                        f"{py_file.relative_to(PKG_DIR)}:{node.name} has {func_len} lines (exceeds {MAX_FUNC_LINES})"
                    )

    assert not violations, "Universal function line limit violations:\n" + "\n".join(violations)
