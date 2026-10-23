"""pdf_goon — Public API: process(), version, re-exports."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pdf_goon.core import process_batch
from pdf_goon.models import VERSION, Config, ProcessResult, make_config

# Configure pypdf decompression limits for high-resolution print/comic scans (up to 256MB)
try:
    import pypdf.filters

    _SAFE_BUFFER_LIMIT = 256 * 1024 * 1024
    if hasattr(pypdf.filters, "ZLIB_MAX_OUTPUT_LENGTH"):
        pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH = _SAFE_BUFFER_LIMIT
    if hasattr(pypdf.filters, "FLATE_MAX_BUFFER_SIZE"):
        pypdf.filters.FLATE_MAX_BUFFER_SIZE = _SAFE_BUFFER_LIMIT
except Exception:
    pass

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
    keep_blank: bool = False,
    margin_tolerance: float = 3.0,
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
        keep_blank=keep_blank,
        margin_tolerance=margin_tolerance,
    )
    return process_batch(config, progress_callback=progress_callback)
