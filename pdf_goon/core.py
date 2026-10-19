"""High-level PDF processing orchestration facade."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

# Module-level imports preserved for test mock compatibility (patch("pdf_goon.core.<fn>"))
from pdf_goon.analyze import (
    decide_processing_mode,
    get_image_data,
    get_page_count,
    get_page_info,
)
from pdf_goon.extract import extract_images, render_page
from pdf_goon.files import get_unique_path, trash_or_move, workspace_context
from pdf_goon.models import ImageInfo, PageInfo
from pdf_goon.optimize import optimize_image
from pdf_goon.pipeline import (
    _finalize_extracted_files,
    _finalize_page_files,
    _finalize_rendered_file,
    _print_batch_progress,
    _print_overall_progress,
    _print_page_progress,
    _process_page,
    process_batch,
    process_single_pdf,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal default backends — delegate to module-level imports so that
# unittest.mock.patch("pdf_goon.core.<fn>") continues to intercept calls.
# ---------------------------------------------------------------------------


class _DefaultAnalyzeBackend:
    """Delegates to module-level analyze functions (patchable by tests)."""

    def get_page_count(self, pdf_path: Path) -> int | None:
        return get_page_count(pdf_path)

    def get_image_data(
        self,
        pdf_path: Path,
        page_num: int,
    ) -> tuple[list[ImageInfo], list[str], bool]:
        return get_image_data(pdf_path, page_num)

    def get_page_info(self, pdf_path: Path, page_num: int) -> PageInfo:
        return get_page_info(pdf_path, page_num)

    def open_session(self, pdf_path: Path):
        from pdf_goon.analyze import PypdfSession

        return PypdfSession(pdf_path)


class _DefaultExtractBackend:
    """Delegates to module-level extract_images (patchable by tests)."""

    def extract_images(
        self,
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
    ) -> list[Path]:
        return extract_images(pdf_path, page_num, output_prefix)


class _DefaultRenderBackend:
    """Delegates to module-level render_page (patchable by tests)."""

    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
        dpi: float,
        page_info: PageInfo,
    ) -> list[Path]:
        return render_page(pdf_path, page_num, output_prefix, dpi, page_info)

    def render_batch(
        self,
        pdf_path: Path,
        tasks: list[dict],
    ) -> list[Path]:
        from pdf_goon.extract import render_batch

        return render_batch(pdf_path, tasks)


__all__ = [
    "_DefaultAnalyzeBackend",
    "_DefaultExtractBackend",
    "_DefaultRenderBackend",
    "_finalize_extracted_files",
    "_finalize_page_files",
    "_finalize_rendered_file",
    "_print_batch_progress",
    "_print_overall_progress",
    "_print_page_progress",
    "_process_page",
    "decide_processing_mode",
    "extract_images",
    "get_image_data",
    "get_page_count",
    "get_page_info",
    "get_unique_path",
    "optimize_image",
    "process_batch",
    "process_single_pdf",
    "render_page",
    "trash_or_move",
    "workspace_context",
]
