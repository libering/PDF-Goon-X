"""Progress display helpers for CLI and batch processing."""

from __future__ import annotations

from pathlib import Path

from pdf_goon.models import PROGRESS_BAR_LENGTH


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
        print()


def _print_batch_progress(current: int, total: int, pdf_path: Path) -> None:
    """Print batch-level progress info to stdout."""
    print(f"  [{current}/{total}] {pdf_path.name}", flush=True)


# Backwards compatibility alias
_print_overall_progress = _print_batch_progress
