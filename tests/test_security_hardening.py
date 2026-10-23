"""Unit tests for security hardening fixes (CWE-88, empty stem, and canvas bounds)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdf_goon._render_worker import _render_single_page_to_file
from pdf_goon.models import Config
from pdf_goon.optimize import optimize_image
from pdf_goon.pipeline.single import process_single_pdf


def test_optimize_image_resolves_absolute_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure optimize_image resolves paths to absolute to prevent CLI option injection."""
    monkeypatch.chdir(tmp_path)
    test_file = tmp_path / "test_image.png"
    test_file.write_bytes(b"PNG test data")

    recorded_cmds: list[list[str]] = []

    def mock_run(cmd: list[str]) -> str:
        recorded_cmds.append(cmd)
        return ""

    with (
        patch("pdf_goon.optimize.os.name", "nt"),
        patch("pdf_goon.optimize.get_tool_path", return_value="pingo"),
        patch("pdf_goon.optimize.check_optimizer_available", return_value=True),
    ):
        rel_path = Path("test_image.png")
        optimize_image(rel_path, run=mock_run)

    assert len(recorded_cmds) == 1
    target_arg = recorded_cmds[0][-1]
    assert Path(target_arg).is_absolute()
    assert target_arg == str(test_file.resolve())
    assert not target_arg.startswith("-")


def test_process_single_pdf_normalizes_empty_stem(tmp_path: Path) -> None:
    """Ensure files with empty stem (.pdf) use fallback 'unnamed_pdf' folder name."""
    fake_pdf = tmp_path / ".pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 dummy")

    mock_analyze = MagicMock(spec=["get_page_count", "get_image_data", "get_page_info"])
    mock_analyze.get_page_count.return_value = 1
    mock_analyze.get_image_data.return_value = ([], [], False)
    mock_analyze.get_page_info.return_value = MagicMock(width_pts=100.0, height_pts=100.0)

    config = Config(path=tmp_path, verbose=False, replace=False, optimize=False)

    with (
        patch("pdf_goon.pipeline.single._dispatch_page_execution") as mock_dispatch,
    ):
        mock_dispatch.return_value = []
        result = process_single_pdf(
            fake_pdf,
            tmp_path / "workspace",
            config,
            analyze_backend=mock_analyze,
        )

    assert result.success is True
    # Verify that an 'unnamed_pdf' folder was created in tmp_path
    created_dirs = [p.name for p in tmp_path.iterdir() if p.is_dir() and "unnamed_pdf" in p.name]
    assert len(created_dirs) == 1


def test_render_worker_rejects_giant_canvas() -> None:
    """Ensure render worker aborts before calling page.render if canvas exceeds MAX_RENDER_PIXELS."""
    mock_page = MagicMock()
    mock_page.get_size.return_value = (50000.0, 50000.0)  # 50,000 pt x 50,000 pt

    mock_pdf = MagicMock()
    mock_pdf.__getitem__.return_value = mock_page

    out_file = Path("dummy.png")
    with pytest.raises(ValueError, match="exceed maximum limit"):
        _render_single_page_to_file(mock_pdf, 1, 400.0, out_file)

    # Crucial: verify page.render was NEVER invoked
    mock_page.render.assert_not_called()
