"""Image extraction and page rendering via Poppler."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pdf_goon.models import PageInfo
from pdf_goon.tools import get_tool_path, run_command


def extract_images(
    pdf_path: Path,
    page_num: int,
    output_prefix: Path,
    *,
    run: Callable[[list[str]], str] = run_command,
) -> list[Path]:
    """Extract embedded images from a single PDF page."""
    cmd = [
        get_tool_path("pdfimages"),
        "-png",
        "-j",
        "-f", str(page_num),
        "-l", str(page_num),
        str(pdf_path),
        str(output_prefix),
    ]
    run(cmd)
    return sorted(output_prefix.parent.glob(f"{output_prefix.name}*"))


def render_page(
    pdf_path: Path,
    page_num: int,
    output_prefix: Path,
    dpi: float,
    page_info: PageInfo,
    *,
    run: Callable[[list[str]], str] = run_command,
) -> list[Path]:
    """Render a PDF page to PNG at the specified DPI."""
    target_w = int((page_info.width_pts * dpi) / 72.0)
    target_h = int((page_info.height_pts * dpi) / 72.0)

    cmd = [
        get_tool_path("pdftocairo"),
        "-png",
        "-singlefile",
        "-cropbox",
        "-r", str(dpi),
        "-x", "0",
        "-y", "0",
        "-W", str(target_w),
        "-H", str(target_h),
        "-f", str(page_num),
        "-l", str(page_num),
        str(pdf_path),
        str(output_prefix),
    ]
    run(cmd)
    return sorted(output_prefix.parent.glob(f"{output_prefix.name}*"))
