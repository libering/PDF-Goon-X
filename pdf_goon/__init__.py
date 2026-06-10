"""pdf_goon — Public API: process(), version, re-exports."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pdf_goon.core import process_batch
from pdf_goon.models import VERSION, Config, ProcessResult, make_config

__all__ = ["Config", "ProcessResult", "VERSION", "process"]


def process(
    path: str | Path = ".",
    *,
    verbose: bool = False,
    replace: bool = False,
    optimize: bool = True,
    dpi_text: int = 400,
    min_width: int = 500,
    recursive: bool = False,
    force_render: bool = False,
    debug: bool = False,
    progress_callback: Callable[[int, int, Path], None] | None = None,
) -> list[ProcessResult]:
    """Process PDF files at the given path. Primary public API."""
    config = make_config(
        path=path,
        verbose=verbose,
        replace=replace,
        optimize=optimize,
        dpi_text=dpi_text,
        min_width=min_width,
        recursive=recursive,
        force_render=force_render,
        debug=debug,
    )
    return process_batch(config, progress_callback=progress_callback)
