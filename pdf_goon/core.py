"""Orchestration: process_batch, process_single_pdf."""

from __future__ import annotations

import logging
import os
import re
import shutil
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pdf_goon.backends import AnalyzeBackend, ExtractBackend, RenderBackend

from pdf_goon.analyze import (
    decide_processing_mode,
    get_image_data,
    get_page_count,
    get_page_info,
)
from pdf_goon.extract import extract_images, render_page
from pdf_goon.files import get_unique_path, trash_or_move, workspace_context
from pdf_goon.models import (
    PROGRESS_BAR_LENGTH,
    Config,
    ImageInfo,
    PageInfo,
    PageResult,
    ProcessingMode,
    ProcessResult,
)
from pdf_goon.optimize import optimize_image

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


def process_batch(
    config: Config,
    *,
    progress_callback: Callable[[int, int, Path], None] | None = None,
    analyze_backend: AnalyzeBackend | None = None,
    extract_backend: ExtractBackend | None = None,
    render_backend: RenderBackend | None = None,
) -> list[ProcessResult]:
    """Process all PDFs matching config. Accepts optional backend overrides."""
    # Instantiate defaults when not provided — uses internal adapters that
    # delegate to module-level imports, preserving mock-patch compatibility.
    _analyze = analyze_backend or _DefaultAnalyzeBackend()
    _extract = extract_backend or _DefaultExtractBackend()
    _render = render_backend or _DefaultRenderBackend()

    # Resolve paths and find PDFs
    root_path = config.path.resolve()

    # Support passing a single PDF file directly
    if root_path.is_file() and root_path.suffix.lower() == ".pdf":
        pdf_files = [root_path]
    else:
        glob_pattern = "**/*.pdf" if config.recursive else "*.pdf"
        pdf_files = [
            f for f in sorted(root_path.glob(glob_pattern)) if "!delete" not in f.parts
        ]

    if not pdf_files:
        return []

    total_files = len(pdf_files)
    results: list[ProcessResult] = []

    # Determine central delete path for recursive mode
    central_delete = (root_path / "!delete") if config.recursive else None

    with workspace_context() as workspace:
        for index, pdf_path in enumerate(pdf_files, 1):
            if progress_callback is not None:
                progress_callback(index, total_files, pdf_path)

            try:
                result = process_single_pdf(
                    pdf_path,
                    workspace,
                    config,
                    central_delete=central_delete,
                    analyze_backend=_analyze,
                    extract_backend=_extract,
                    render_backend=_render,
                )
            except Exception as exc:
                logger.error("Unexpected error processing %s: %s", pdf_path.name, exc)
                result = ProcessResult(
                    pdf_path=pdf_path,
                    success=False,
                    error=f"Unexpected error: {exc}",
                )

            results.append(result)

            # Print progress bar to stdout if not verbose
            if not config.verbose:
                _print_batch_progress(index, total_files, pdf_path)

    return results


def process_single_pdf(
    pdf_path: Path,
    workspace: Path,
    config: Config,
    *,
    central_delete: Path | None = None,
    analyze_backend: AnalyzeBackend | None = None,
    extract_backend: ExtractBackend | None = None,
    render_backend: RenderBackend | None = None,
) -> ProcessResult:
    """Process one PDF file. Returns structured result."""
    _analyze = analyze_backend or _DefaultAnalyzeBackend()
    _extract = extract_backend or _DefaultExtractBackend()
    _render = render_backend or _DefaultRenderBackend()

    # Guard: file must exist
    if not pdf_path.exists():
        return ProcessResult(pdf_path=pdf_path, success=False, error="File not found")

    # Guard: must be readable and have pages
    page_count = _analyze.get_page_count(pdf_path)
    if page_count is None:
        return ProcessResult(
            pdf_path=pdf_path, success=False, error="Cannot read page count"
        )

    if page_count == 0:
        return ProcessResult(
            pdf_path=pdf_path, success=False, error="PDF has zero pages"
        )

    # Create output directory
    base_output_path = pdf_path.parent / pdf_path.stem
    output_dir = get_unique_path(base_output_path, is_dir=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("  Processing: %s (%d pages)", pdf_path.name, page_count)

    # Process each page in parallel
    page_results: list[PageResult] = []
    completed_pages = 0
    max_workers = min(32, os.cpu_count() or 1)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_page,
                pdf_path,
                page,
                page_count,
                workspace,
                output_dir,
                config,
                _analyze,
                _extract,
                _render,
            ): page
            for page in range(1, page_count + 1)
        }

        for future in as_completed(futures):
            page_results.append(future.result())
            completed_pages += 1
            if not config.verbose:
                _print_page_progress(completed_pages, page_count)

    # Sort results since as_completed yields them out of order
    page_results.sort(key=lambda r: r.page_num)

    # Handle source PDF replacement
    if config.replace:
        delete_dir = central_delete if central_delete else None
        trash_or_move(pdf_path, delete_dir)

    return ProcessResult(
        pdf_path=pdf_path,
        success=True,
        pages_processed=page_count,
    )


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
) -> PageResult:
    """Process a single page: analyze, extract/render, optimize, rename."""
    _analyze = analyze_backend or _DefaultAnalyzeBackend()
    _extract = extract_backend or _DefaultExtractBackend()
    _render = render_backend or _DefaultRenderBackend()

    try:
        local_prefix = workspace / f"page_{page}_tmp"

        # Analyze
        images, mask_indices, has_text = _analyze.get_image_data(pdf_path, page)
        page_info = _analyze.get_page_info(pdf_path, page)

        # Decide processing mode
        decision = decide_processing_mode(
            images,
            page_info,
            config.min_width,
            config.dpi_text,
            config.force_render,
            has_text=has_text,
            keep_blank=config.keep_blank,
        )

        logger.info("    Page %02d: %s", page, decision.reason)

        # Skip blank pages — no extract or render needed
        if decision.mode == ProcessingMode.BLANK:
            logger.info("    Page %02d: Blank page, skipping", page)
            return PageResult(
                page_num=page,
                mode=ProcessingMode.BLANK,
                files_produced=(),
            )

        # Execute extraction or rendering
        was_rendered = False
        if decision.mode == ProcessingMode.EXTRACT:
            generated_files = _extract.extract_images(pdf_path, page, local_prefix)
            logger.info("    Page %02d: Extracting ...", page)
        else:
            render_prefix = workspace / f"render_{page}_tmp"
            generated_files = _render.render_page(
                pdf_path,
                page,
                render_prefix,
                decision.dpi,
                page_info,
            )
            was_rendered = True
            target_w = int((page_info.width_pts * decision.dpi) / 72.0)
            target_h = int((page_info.height_pts * decision.dpi) / 72.0)
            logger.info(
                "    Page %02d: Rendering @ %dx%d px ...", page, target_w, target_h
            )

        # Use the file list returned by extract/render directly (no glob)
        output_files = _finalize_page_files(
            generated_files, mask_indices, was_rendered, page, output_dir, config
        )

        return PageResult(
            page_num=page,
            mode=decision.mode,
            files_produced=tuple(output_files),
        )
    except Exception as exc:
        logger.error("    Page %02d: Unexpected error: %s", page, exc)
        return PageResult(
            page_num=page,
            mode=ProcessingMode.RENDER,  # Fallback mode indicator
            files_produced=(),
            error=str(exc),
        )


def _finalize_rendered_file(
    generated_files: list[Path],
    page: int,
    output_dir: Path,
    config: Config,
) -> list[Path]:
    """RENDER path: optimize → rename with _r suffix → move to output.

    pdftocairo -singlefile produces one file per page without a digit suffix.
    We filter by known image extensions, run lossless optimization if enabled,
    then rename to the convention {page:03d}_r{ext} before moving to output_dir.
    """
    output_files: list[Path] = []

    for local_file in generated_files:
        suffix = local_file.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg"):
            continue

        # Lossless optimization when enabled
        if config.optimize:
            optimize_image(local_file)

        # RENDER always produces one file per page — rename to {page:03d}_r{suffix}
        dest_name = f"{page:03d}_r{suffix}"
        dest_path = output_dir / dest_name
        shutil.move(str(local_file), str(dest_path))
        output_files.append(dest_path)

    return output_files


def _finalize_extracted_files(
    generated_files: list[Path],
    mask_indices: list[str],
    page: int,
    output_dir: Path,
    config: Config,
) -> list[Path]:
    """EXTRACT path: filter masks → optimize → rename with page number → move."""
    output_files: list[Path] = []
    for local_file in generated_files:
        # pdfimages output format: prefix-{NNN}.{ext}
        match = re.search(r"-(\d+)\.(?:png|jpg|jpeg)$", local_file.name, re.IGNORECASE)
        if not match:
            continue

        file_idx_str = match.group(1)

        # Filter mask files identified by analyze step
        if file_idx_str.zfill(3) in mask_indices:
            logger.debug("      Deleting mask: %s", local_file.name)
            local_file.unlink()
            continue

        suffix = local_file.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg"):
            continue

        # Lossless optimization when enabled
        if config.optimize:
            optimize_image(local_file)

        # Primary naming: {page:03d}{suffix}
        dest_name = f"{page:03d}{suffix}"
        dest_path = output_dir / dest_name

        # Handle multiple extracted images per page (sub-image naming)
        if dest_path.exists():
            sub_idx = re.search(r"-(\d+)\.[^.]+$", local_file.name)
            if sub_idx:
                dest_name = f"{page:03d}_{sub_idx.group(1)}{suffix}"
                dest_path = output_dir / dest_name

        shutil.move(str(local_file), str(dest_path))
        output_files.append(dest_path)

    return output_files


def _finalize_page_files(
    generated_files: list[Path],
    mask_indices: list[str],
    was_rendered: bool,
    page: int,
    output_dir: Path,
    config: Config,
) -> list[Path]:
    """Dispatcher: delegates to render or extract finalization."""
    if was_rendered:
        return _finalize_rendered_file(generated_files, page, output_dir, config)
    return _finalize_extracted_files(
        generated_files, mask_indices, page, output_dir, config
    )


def _print_page_progress(page: int, total_pages: int) -> None:
    """Print per-page progress bar to stdout."""
    percent = (page / total_pages) * 100
    filled_length = int(PROGRESS_BAR_LENGTH * page // total_pages)
    bar = "█" * filled_length + "-" * (PROGRESS_BAR_LENGTH - filled_length)
    print(
        f"\r    Progress: |{bar}| {percent:.1f}% (Page {page}/{total_pages})",
        end="",
        flush=True,
    )
    if page == total_pages:
        print()  # newline after completion


def _print_batch_progress(current: int, total: int, pdf_path: Path) -> None:
    """Print batch-level progress info to stdout."""
    print(f"  [{current}/{total}] {pdf_path.name}", flush=True)
