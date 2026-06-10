"""Orchestration: process_batch, process_single_pdf."""

from __future__ import annotations

import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path

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
    PageResult,
    ProcessingMode,
    ProcessResult,
    ToolNotFoundError,
)
from pdf_goon.optimize import optimize_image
from pdf_goon.tools import check_poppler_available

logger = logging.getLogger(__name__)


def process_batch(
    config: Config,
    *,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> list[ProcessResult]:
    """Process all PDFs matching config. Main orchestration loop."""
    # Check poppler availability before starting
    missing = check_poppler_available()
    if missing:
        raise ToolNotFoundError(missing)

    # Resolve paths and find PDFs
    root_path = config.path.resolve()
    glob_pattern = "**/*.pdf" if config.recursive else "*.pdf"
    pdf_files = [
        f for f in sorted(root_path.glob(glob_pattern))
        if "!delete" not in f.parts
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
) -> ProcessResult:
    """Process one PDF file. Returns structured result."""
    # Guard: file must exist
    if not pdf_path.exists():
        return ProcessResult(pdf_path=pdf_path, success=False, error="File not found")

    # Guard: must be readable and have pages
    page_count = get_page_count(pdf_path)
    if page_count is None:
        return ProcessResult(pdf_path=pdf_path, success=False, error="Cannot read page count")

    if page_count == 0:
        return ProcessResult(pdf_path=pdf_path, success=False, error="PDF has zero pages")

    # Create output directory
    base_output_path = pdf_path.parent / pdf_path.stem
    output_dir = get_unique_path(base_output_path, is_dir=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("  Processing: %s (%d pages)", pdf_path.name, page_count)

    # Process each page
    page_results: list[PageResult] = []
    for page in range(1, page_count + 1):
        page_result = _process_page(pdf_path, page, page_count, workspace, output_dir, config)
        page_results.append(page_result)

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
) -> PageResult:
    """Process a single page: analyze, extract/render, optimize, rename."""
    local_prefix = workspace / f"page_{page}_tmp"

    # Analyze
    images, mask_indices = get_image_data(pdf_path, page)
    page_info = get_page_info(pdf_path, page)

    # Decide processing mode
    decision = decide_processing_mode(
        images, page_info, config.min_width, config.dpi_text, config.force_render,
    )

    logger.info("    Page %02d: %s", page, decision.reason)

    # Execute extraction or rendering
    was_rendered = False
    if decision.mode == ProcessingMode.EXTRACT:
        generated_files = extract_images(pdf_path, page, local_prefix)
        logger.info("    Page %02d: Extracting ...", page)
    else:
        render_prefix = workspace / f"render_{page}_tmp"
        generated_files = render_page(pdf_path, page, render_prefix, decision.dpi, page_info)
        was_rendered = True
        target_w = int((page_info.width_pts * decision.dpi) / 72.0)
        target_h = int((page_info.height_pts * decision.dpi) / 72.0)
        logger.info("    Page %02d: Rendering @ %dx%d px ...", page, target_w, target_h)

    # Print per-page progress bar if not verbose
    if not config.verbose:
        _print_page_progress(page, total_pages)

    # Use the file list returned by extract/render directly (no glob)
    output_files = _finalize_page_files(generated_files, mask_indices, was_rendered, page, output_dir, config)

    return PageResult(
        page_num=page,
        mode=decision.mode,
        files_produced=tuple(output_files),
    )


def _finalize_page_files(
    generated_files: list[Path],
    mask_indices: list[str],
    was_rendered: bool,
    page: int,
    output_dir: Path,
    config: Config,
) -> list[Path]:
    """Filter masks, optimize, rename and move files to output directory."""
    output_files: list[Path] = []
    for local_file in generated_files:
        # Match pdfimages/pdftocairo output pattern
        match = re.search(r"-(\d+)\.(?:png|jpg|jpeg)$", local_file.name, re.IGNORECASE)
        if not match:
            continue

        file_idx_str = match.group(1)

        # Filter mask files (only for extraction, not rendering)
        if not was_rendered and file_idx_str.zfill(3) in mask_indices:
            logger.debug("      Deleting mask: %s", local_file.name)
            local_file.unlink()
            continue

        suffix = local_file.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg"):
            continue

        # Optimize if enabled
        if config.optimize:
            optimize_image(local_file)

        # Rename and move to output directory
        render_tag = "_r" if was_rendered else ""
        dest_name = f"{page:03d}{render_tag}{suffix}"
        dest_path = output_dir / dest_name

        # Handle multiple files per page (sub-image naming)
        if dest_path.exists():
            sub_idx = re.search(r"-(\d+)\.[^.]+$", local_file.name)
            if sub_idx:
                dest_name = f"{page:03d}_{sub_idx.group(1)}{render_tag}{suffix}"
                dest_path = output_dir / dest_name

        shutil.move(str(local_file), str(dest_path))
        output_files.append(dest_path)

    return output_files


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
