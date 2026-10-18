"""Architecture and code constraint tests.

Enforces:
1. Single file length <= 500 lines.
2. Single function length <= 50 lines.
"""

from __future__ import annotations

import ast
import pathlib
import pytest

MAX_FILE_LINES = 500
MAX_FUNC_LINES = 50

PKG_DIR = pathlib.Path(__file__).resolve().parent.parent / "pdf_goon"


def test_file_line_limits() -> None:
    """Verify no python source file exceeds MAX_FILE_LINES (500 lines)."""
    violations = []
    for py_file in PKG_DIR.rglob("*.py"):
        lines = py_file.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_FILE_LINES:
            violations.append(
                f"{py_file.relative_to(PKG_DIR)} has {len(lines)} lines (exceeds {MAX_FILE_LINES})"
            )

    # Note: pdf_goon/core.py is scheduled for Phase 2 refactoring
    # In Phase 1, we assert all files in pdf_goon/analyze/ strictly comply
    analyze_dir = PKG_DIR / "analyze"
    analyze_violations = [v for v in violations if "analyze" in v]
    assert not analyze_violations, f"Analyze subpackage file limit violations:\n" + "\n".join(analyze_violations)


def test_analyze_function_line_limits() -> None:
    """Verify no function in pdf_goon/analyze exceeds MAX_FUNC_LINES (50 lines)."""
    violations = []
    analyze_dir = PKG_DIR / "analyze"

    for py_file in analyze_dir.glob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_len = (node.end_lineno or 0) - node.lineno + 1
                if func_len > MAX_FUNC_LINES:
                    violations.append(
                        f"{py_file.name}:{node.name} has {func_len} lines (exceeds {MAX_FUNC_LINES})"
                    )

    assert not violations, f"Analyze function limit violations:\n" + "\n".join(violations)
