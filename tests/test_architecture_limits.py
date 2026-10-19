"""Architecture and code constraint tests.

Enforces across refactored modules in pdf_goon:
1. Universal: Single file length <= 500 lines across the entire codebase.
2. Refactored architecture: Single function length <= 50 lines in analyze, pipeline, and core.
"""

from __future__ import annotations

import ast
import pathlib
import pytest

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

    assert not violations, f"File line limit violations:\n" + "\n".join(violations)


def test_core_architecture_function_line_limits() -> None:
    """Verify NO function in analyze, pipeline, or core exceeds MAX_FUNC_LINES (50 lines)."""
    violations = []
    target_dirs = [PKG_DIR / "analyze", PKG_DIR / "pipeline"]
    target_files = [PKG_DIR / "core.py"]

    py_files = target_files.copy()
    for d in target_dirs:
        py_files.extend(d.glob("*.py"))

    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_len = (node.end_lineno or 0) - node.lineno + 1
                if func_len > MAX_FUNC_LINES:
                    violations.append(
                        f"{py_file.relative_to(PKG_DIR)}:{node.name} has {func_len} lines (exceeds {MAX_FUNC_LINES})"
                    )

    assert not violations, f"Function line limit violations:\n" + "\n".join(violations)
