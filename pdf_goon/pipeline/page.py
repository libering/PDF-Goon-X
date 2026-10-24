"""Single-page processing pipeline: analyze, extract/render, optimize, rename."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdf_goon.backends import AnalyzeBackend, ExtractBackend, RenderBackend

from pdf_goon.analyze import decide_processing_mode as _default_decide_mode
from pdf_goon.models import (
    Config,
    ImageInfo,
    PageDecision,
    PageInfo,
    PageResult,
    ProcessingMode,
)
from pdf_goon.pipeline.finalize import _finalize_page_files

logger = logging.getLogger(__name__)


def _resolve_decide_mode() -> Callable:
    """Dynamically resolve decide_processing_mode hook from pdf_goon.core if patched."""
    core = sys.modules.get("pdf_goon.core")
    return (
        getattr(core, "decide_processing_mode", _default_decide_mode)
        if core
        else _default_decide_mode
    )


def _resolve_backends(
    analyze_backend: AnalyzeBackend | None,
    extract_backend: ExtractBackend | None,
    render_backend: RenderBackend | None,
) -> tuple[Any, Any, Any]:
    """Resolve backends with fallback to pdf_goon.core default backend classes."""
    core = sys.modules.get("pdf_goon.core")
    if core is not None:
        _analyze = analyze_backend or getattr(core, "_DefaultAnalyzeBackend")()
        _extract = extract_backend or getattr(core, "_DefaultExtractBackend")()
        _render = render_backend or getattr(core, "_DefaultRenderBackend")()
    else:
        raise RuntimeError("pdf_goon.core must be loaded for default backend resolution")
    return _analyze, _extract, _render


def _obtain_page_decision(
    pdf_path: Path,
    page: int,
    config: Config,
    analyze_backend: Any,
    decision_info: (
        tuple[PageDecision, list[ImageInfo], list[str], PageInfo] | None
    ),
) -> tuple[PageDecision, list[ImageInfo], list[str], PageInfo]:
    """Retrieve existing decision or perform on-demand page inspection."""
    if decision_info is not None:
        return decision_info

    images, mask_indices, has_text = analyze_backend.get_image_data(pdf_path, page)
    page_info = analyze_backend.get_page_info(pdf_path, page)
    decide_fn = _resolve_decide_mode()
    decision = decide_fn(
        images,
        page_info,
        config.min_width,
        config.dpi_text,
        config.force_render,
        has_text=has_text,
        keep_blank=config.keep_blank,
        margin_tolerance=config.margin_tolerance,
    )
    return decision, images, mask_indices, page_info


def _execute_page_action(
    pdf_path: Path,
    page: int,
    workspace: Path,
    decision: PageDecision,
    page_info: PageInfo,
    extract_backend: Any,
    render_backend: Any,
    extract_session: Any = None,
) -> tuple[list[Path], bool]:
    """Execute either image extraction or full-page rendering."""
    if decision.mode == ProcessingMode.EXTRACT:
        local_prefix = workspace / f"page_{page}_tmp"
        logger.info("    Page %02d: Extracting ...", page)
        if extract_session is not None and hasattr(extract_session, "extract_images"):
            return extract_session.extract_images(page, local_prefix), False
        return extract_backend.extract_images(pdf_path, page, local_prefix), False

    render_prefix = workspace / f"render_{page}_tmp"
    target_w = int((page_info.width_pts * decision.dpi) / 72.0)
    target_h = int((page_info.height_pts * decision.dpi) / 72.0)
    logger.info("    Page %02d: Rendering @ %dx%d px ...", page, target_w, target_h)
    files = render_backend.render_page(
        pdf_path, page, render_prefix, decision.dpi, page_info
    )
    return files, True


def _process_page(
    pdf_path: Path,
    page: int,
    total_pages: int,
    workspace: Path,
    output_dir: Path,
    config: Config,
    analyze_backend: AnalyzeBackend | None = None,
    extract_backend: ExtractBackend | None = None,
    render_backend: RenderBackend | None = None,
    *,
    decision_info: (
        tuple[PageDecision, list[ImageInfo], list[str], PageInfo] | None
    ) = None,
    extract_session: Any = None,
) -> PageResult:
    """Process a single page: analyze, extract/render, optimize, rename."""
    try:
        _analyze, _extract, _render = _resolve_backends(
            analyze_backend, extract_backend, render_backend
        )
        decision, images, mask_indices, page_info = _obtain_page_decision(
            pdf_path, page, config, _analyze, decision_info
        )
        logger.info("    Page %02d: %s", page, decision.reason)

        if decision.mode == ProcessingMode.BLANK:
            logger.info("    Page %02d: Blank page, skipping", page)
            return PageResult(page_num=page, mode=ProcessingMode.BLANK, files_produced=())

        generated_files, was_rendered = _execute_page_action(
            pdf_path, page, workspace, decision, page_info, _extract, _render, extract_session
        )
        output_files = _finalize_page_files(
            generated_files, mask_indices, was_rendered, page, output_dir, config
        )
        if not output_files:
            err_msg = f"Zero files produced for page {page} with mode {decision.mode.value}"
            logger.error("    Page %02d: %s", page, err_msg)
            return PageResult(
                page_num=page, mode=decision.mode, files_produced=(), error=err_msg
            )
        return PageResult(
            page_num=page, mode=decision.mode, files_produced=tuple(output_files)
        )
    except Exception as exc:
        logger.error("    Page %02d: Unexpected error: %s", page, exc)
        return PageResult(
            page_num=page, mode=ProcessingMode.RENDER, files_produced=(), error=str(exc)
        )
