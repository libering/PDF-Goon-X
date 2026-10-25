"""Single PDF processing lifecycle: analysis, dispatch, batch rendering, and finalization."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdf_goon.backends import AnalyzeBackend, ExtractBackend, RenderBackend

from pdf_goon.backends import BatchRenderBackend
from pdf_goon.files import get_unique_path, trash_or_move
from pdf_goon.models import (
    Config,
    ImageInfo,
    PageDecision,
    PageInfo,
    PageResult,
    ProcessingMode,
    ProcessResult,
)
from pdf_goon.pipeline.finalize import _finalize_page_files
from pdf_goon.pipeline.page import _process_page, _resolve_backends, _resolve_decide_mode
from pdf_goon.pipeline.progress import _print_page_progress

logger = logging.getLogger(__name__)


def _validate_pdf_input(
    pdf_path: Path, analyze_backend: Any
) -> tuple[bool, int, str | None]:
    """Validate PDF existence and page count."""
    if not pdf_path.exists():
        return False, 0, "File not found"
    page_count = analyze_backend.get_page_count(pdf_path)
    if page_count is None:
        return False, 0, "Cannot read page count"
    if page_count == 0:
        return False, 0, "PDF has zero pages"
    return True, page_count, None


def _analyze_pages_phase(
    pdf_path: Path, page_count: int, analyze_backend: Any, config: Config
) -> dict[int, tuple[PageDecision, list[ImageInfo], list[str], PageInfo]]:
    """Phase 1: Sequential Analysis Session holding open handles."""
    decisions: dict[int, tuple[PageDecision, list[ImageInfo], list[str], PageInfo]] = {}
    session = None
    if hasattr(analyze_backend, "open_session"):
        try:
            session = analyze_backend.open_session(pdf_path)
        except Exception as e:
            logger.warning("Could not open analysis session: %s", e)
            session = None

    decide_fn = _resolve_decide_mode()
    try:
        for page in range(1, page_count + 1):
            if session is not None:
                images, mask_indices, has_text, page_info = session.inspect_page(page)
            else:
                images, mask_indices, has_text = analyze_backend.get_image_data(pdf_path, page)
                page_info = analyze_backend.get_page_info(pdf_path, page)

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
            decisions[page] = (decision, images, mask_indices, page_info)
    finally:
        if session is not None:
            session.close()

    return decisions


def _render_batch_pages(
    pdf_path: Path,
    render_tasks: list[dict],
    render_pages: list[int],
    decisions: dict,
    workspace: Path,
    output_dir: Path,
    config: Config,
    render_backend: Any,
    page_count: int,
    completed_pages: int,
) -> tuple[list[PageResult], int]:
    """Execute batch render and finalization of rendered files."""
    results: list[PageResult] = []
    from pdf_goon.concurrency import resolve_worker_count

    effective_workers = resolve_worker_count(config.jobs, len(render_tasks))
    try:
        render_backend.render_batch(
            pdf_path, render_tasks, max_workers=effective_workers
        )
    except TypeError:
        render_backend.render_batch(pdf_path, render_tasks)
    for page in render_pages:
        decision, _, mask_indices, page_info = decisions[page]
        logger.info("    Page %02d: %s", page, decision.reason)
        target_w = int((page_info.width_pts * decision.dpi) / 72.0)
        target_h = int((page_info.height_pts * decision.dpi) / 72.0)
        logger.info("    Page %02d: Rendering @ %dx%d px ...", page, target_w, target_h)
        out_file = (workspace / f"render_{page}_tmp").with_suffix(".png")
        output_files = _finalize_page_files(
            [out_file], mask_indices, True, page, output_dir, config
        )
        results.append(
            PageResult(
                page_num=page,
                mode=ProcessingMode.RENDER,
                files_produced=tuple(output_files),
            )
        )
        completed_pages += 1
        if not config.verbose:
            _print_page_progress(completed_pages, page_count)
    return results, completed_pages


def _render_fallback_pages(
    pdf_path: Path,
    render_pages: list[int],
    decisions: dict,
    workspace: Path,
    output_dir: Path,
    config: Config,
    analyze_backend: Any,
    extract_backend: Any,
    render_backend: Any,
    page_count: int,
    completed_pages: int,
) -> tuple[list[PageResult], int]:
    """Execute per-page render fallback when batch rendering is unsupported or fails."""
    results: list[PageResult] = []
    for page in render_pages:
        res = _process_page(
            pdf_path,
            page,
            page_count,
            workspace,
            output_dir,
            config,
            analyze_backend,
            extract_backend,
            render_backend,
            decision_info=decisions[page],
        )
        results.append(res)
        completed_pages += 1
        if not config.verbose:
            _print_page_progress(completed_pages, page_count)
    return results, completed_pages


def _execute_render_phase(
    pdf_path: Path,
    render_tasks: list[dict],
    render_pages: list[int],
    decisions: dict,
    workspace: Path,
    output_dir: Path,
    config: Config,
    analyze_backend: Any,
    extract_backend: Any,
    render_backend: Any,
    page_count: int,
    completed_pages: int,
) -> list[PageResult]:
    """Execute batch rendering with per-page fallback."""
    if not render_tasks:
        return []

    if isinstance(render_backend, BatchRenderBackend) and len(render_tasks) > 1:
        try:
            results, _ = _render_batch_pages(
                pdf_path, render_tasks, render_pages, decisions,
                workspace, output_dir, config, render_backend, page_count, completed_pages,
            )
            return results
        except Exception as exc:
            logger.warning("Batch render failed, falling back to per-page render: %s", exc)

    results, _ = _render_fallback_pages(
        pdf_path, render_pages, decisions,
        workspace, output_dir, config, analyze_backend, extract_backend, render_backend,
        page_count, completed_pages,
    )
    return results


def _open_extract_session(extract_backend: Any, pdf_path: Path) -> Any:
    """Attempt opening a sequential extraction session."""
    if hasattr(extract_backend, "open_session"):
        try:
            return extract_backend.open_session(pdf_path)
        except Exception as e:
            logger.warning("Could not open extraction session: %s", e)
    return None


def _append_render_task(
    workspace: Path, page: int, decision: Any, tiles: bool,
    tasks: list[dict], pages: list[int],
) -> None:
    """Register a render task and record page number."""
    out_file = (workspace / f"render_{page}_tmp").with_suffix(".png")
    tasks.append({"page": page, "dpi": decision.dpi, "out": str(out_file), "tiles": tiles})
    pages.append(page)


def _process_immediate_pages(
    pdf_path: Path,
    page_count: int,
    decisions: dict,
    workspace: Path,
    output_dir: Path,
    config: Config,
    analyze_backend: Any,
    extract_backend: Any,
    render_backend: Any,
) -> tuple[list[PageResult], list[dict], list[int], int]:
    """Process blank and extract pages immediately, queuing render pages."""
    page_results: list[PageResult] = []
    render_tasks: list[dict] = []
    render_pages: list[int] = []
    completed_pages = 0

    extract_session = _open_extract_session(extract_backend, pdf_path)
    try:
        for page in range(1, page_count + 1):
            decision, _, _, _ = decisions[page]
            if decision.mode == ProcessingMode.BLANK:
                logger.info("    Page %02d: %s\n    Page %02d: Blank page, skipping", page, decision.reason, page)
                page_results.append(PageResult(page_num=page, mode=ProcessingMode.BLANK, files_produced=()))
                completed_pages += 1
            elif decision.mode == ProcessingMode.EXTRACT:
                res = _process_page(
                    pdf_path, page, page_count, workspace, output_dir, config,
                    analyze_backend, extract_backend, render_backend,
                    decision_info=decisions[page],
                    extract_session=extract_session,
                )
                page_results.append(res)
                completed_pages += 1
            else:
                _append_render_task(workspace, page, decision, config.tiles, render_tasks, render_pages)
                continue

            if not config.verbose:
                _print_page_progress(completed_pages, page_count)
    finally:
        if extract_session is not None and hasattr(extract_session, "close"):
            try:
                extract_session.close()
            except Exception:
                pass

    return page_results, render_tasks, render_pages, completed_pages



def _dispatch_page_execution(
    pdf_path: Path,
    page_count: int,
    decisions: dict,
    workspace: Path,
    output_dir: Path,
    config: Config,
    analyze_backend: Any,
    extract_backend: Any,
    render_backend: Any,
) -> list[PageResult]:
    """Phase 2: Dispatched Execution across blank, extract, and render modes."""
    immediate_results, render_tasks, render_pages, completed_pages = (
        _process_immediate_pages(
            pdf_path,
            page_count,
            decisions,
            workspace,
            output_dir,
            config,
            analyze_backend,
            extract_backend,
            render_backend,
        )
    )
    render_results = _execute_render_phase(
        pdf_path,
        render_tasks,
        render_pages,
        decisions,
        workspace,
        output_dir,
        config,
        analyze_backend,
        extract_backend,
        render_backend,
        page_count,
        completed_pages,
    )
    all_results = immediate_results + render_results
    all_results.sort(key=lambda r: r.page_num)
    return all_results


def _resolve_output_dir(pdf_path: Path) -> Path:
    raw_stem = pdf_path.stem.strip()
    stem = "unnamed_pdf" if (not raw_stem or raw_stem.startswith(".")) else raw_stem
    return get_unique_path(pdf_path.parent / stem, is_dir=True)


def process_single_pdf(
    pdf_path: Path,
    workspace: Path,
    config: Config,
    *,
    central_delete: Path | None = None,
    analyze_backend: AnalyzeBackend | None = None,
    extract_backend: ExtractBackend | None = None,
    render_backend: RenderBackend | None = None,
    output_dir: Path | None = None,
) -> ProcessResult:
    """Process one PDF file. Returns structured result."""
    _analyze, _extract, _render = _resolve_backends(
        analyze_backend, extract_backend, render_backend
    )
    valid, page_count, err = _validate_pdf_input(pdf_path, _analyze)
    if not valid:
        return ProcessResult(pdf_path=pdf_path, success=False, error=err)

    target_dir = output_dir if output_dir is not None else _resolve_output_dir(pdf_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info("  Processing: %s (%d pages)", pdf_path.name, page_count)

    decisions = _analyze_pages_phase(pdf_path, page_count, _analyze, config)
    _dispatch_page_execution(
        pdf_path,
        page_count,
        decisions,
        workspace,
        target_dir,
        config,
        _analyze,
        _extract,
        _render,
    )

    if config.replace:
        delete_dir = central_delete if central_delete else None
        trash_or_move(pdf_path, delete_dir)

    return ProcessResult(pdf_path=pdf_path, success=True, pages_processed=page_count)

