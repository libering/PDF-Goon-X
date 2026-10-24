"""Batch PDF processing orchestration across multiple files."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pdf_goon.backends import AnalyzeBackend, ExtractBackend, RenderBackend

from pdf_goon.concurrency import execute_parallel_tasks, resolve_worker_count
from pdf_goon.files import workspace_context as _default_workspace_context
from pdf_goon.models import Config, ProcessResult
from pdf_goon.pipeline.page import _resolve_backends
from pdf_goon.pipeline.progress import _print_batch_progress
from pdf_goon.pipeline.single import process_single_pdf

logger = logging.getLogger(__name__)


def _resolve_workspace_context() -> Callable:
    """Dynamically resolve workspace_context hook from pdf_goon.core if patched."""
    core = sys.modules.get("pdf_goon.core")
    return (
        getattr(core, "workspace_context", _default_workspace_context)
        if core
        else _default_workspace_context
    )


def _discover_batch_targets(config: Config) -> tuple[list[Path], Path | None]:
    """Find matching PDF files and central delete directory from config."""
    root_path = config.path.resolve()
    if root_path.is_file() and root_path.suffix.lower() == ".pdf":
        pdf_files = [root_path]
    else:
        glob_pattern = "**/*.pdf" if config.recursive else "*.pdf"
        pdf_files = [
            f for f in sorted(root_path.glob(glob_pattern)) if "!delete" not in f.parts
        ]

    central_delete = (root_path / "!delete") if config.recursive else None
    return pdf_files, central_delete


def _process_batch_item(
    pdf_path: Path,
    index: int,
    total_files: int,
    workspace: Path,
    config: Config,
    central_delete: Path | None,
    analyze_backend: Any,
    extract_backend: Any,
    render_backend: Any,
    progress_callback: Callable[[int, int, Path], None] | None,
) -> ProcessResult:
    """Execute single PDF processing inside batch loop with error isolation."""
    if progress_callback is not None:
        progress_callback(index, total_files, pdf_path)

    try:
        result = process_single_pdf(
            pdf_path,
            workspace,
            config,
            central_delete=central_delete,
            analyze_backend=analyze_backend,
            extract_backend=extract_backend,
            render_backend=render_backend,
        )
    except Exception as exc:
        logger.error("Unexpected error processing %s: %s", pdf_path.name, exc)
        result = ProcessResult(
            pdf_path=pdf_path,
            success=False,
            error=f"Unexpected error: {exc}",
        )

    if not config.verbose:
        _print_batch_progress(index, total_files, pdf_path)

    return result


def _parallel_batch_worker(
    task: tuple[Path, Config, Path | None],
) -> ProcessResult:
    """Isolated worker entry point for parallel batch execution."""
    pdf_path, config, central_delete = task
    from pdf_goon.files import workspace_context

    try:
        with workspace_context() as workspace:
            return process_single_pdf(
                pdf_path,
                workspace,
                config,
                central_delete=central_delete,
            )
    except Exception as exc:
        logger.error("Unexpected error processing %s in worker: %s", pdf_path.name, exc)
        return ProcessResult(
            pdf_path=pdf_path,
            success=False,
            error=f"Unexpected error: {exc}",
        )


def _process_batch_parallel(
    pdf_files: list[Path],
    config: Config,
    central_delete: Path | None,
    max_workers: int,
    progress_callback: Callable[[int, int, Path], None] | None,
) -> list[ProcessResult]:
    """Execute batch items across worker pool with progress notification."""
    tasks = [(pdf, config, central_delete) for pdf in pdf_files]

    def on_progress(completed: int, total: int, res: ProcessResult) -> None:
        if progress_callback is not None:
            progress_callback(completed, total, res.pdf_path)
        if not config.verbose:
            _print_batch_progress(completed, total, res.pdf_path)

    return execute_parallel_tasks(
        tasks,
        _parallel_batch_worker,
        max_workers=max_workers,
        progress_callback=on_progress,
    )


def _process_batch_sequential(
    pdf_files: list[Path],
    config: Config,
    central_delete: Path | None,
    analyze_backend: Any,
    extract_backend: Any,
    render_backend: Any,
    progress_callback: Callable[[int, int, Path], None] | None,
) -> list[ProcessResult]:
    """Process all PDFs sequentially in the current process."""
    _analyze, _extract, _render = _resolve_backends(
        analyze_backend, extract_backend, render_backend
    )
    total_files = len(pdf_files)
    results: list[ProcessResult] = []
    ws_ctx = _resolve_workspace_context()

    with ws_ctx() as workspace:
        for index, pdf_path in enumerate(pdf_files, 1):
            res = _process_batch_item(
                pdf_path,
                index,
                total_files,
                workspace,
                config,
                central_delete,
                _analyze,
                _extract,
                _render,
                progress_callback,
            )
            results.append(res)
    return results


def process_batch(
    config: Config,
    *,
    progress_callback: Callable[[int, int, Path], None] | None = None,
    analyze_backend: AnalyzeBackend | None = None,
    extract_backend: ExtractBackend | None = None,
    render_backend: RenderBackend | None = None,
) -> list[ProcessResult]:
    """Process all PDFs matching config with adaptive concurrency."""
    pdf_files, central_delete = _discover_batch_targets(config)
    if not pdf_files:
        return []

    total_files = len(pdf_files)
    effective_workers = resolve_worker_count(config.jobs, total_files)
    has_custom_backends = any(
        b is not None for b in (analyze_backend, extract_backend, render_backend)
    )

    if effective_workers > 1 and not has_custom_backends:
        return _process_batch_parallel(
            pdf_files, config, central_delete, effective_workers, progress_callback
        )

    return _process_batch_sequential(
        pdf_files,
        config,
        central_delete,
        analyze_backend,
        extract_backend,
        render_backend,
        progress_callback,
    )
