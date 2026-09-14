"""Lossless image optimization (pingo/oxipng/jpegoptim)."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from pdf_goon.models import SubprocessError
from pdf_goon.tools import check_optimizer_available, get_tool_path, run_command

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg"})


def optimize_image(
    image_path: Path, *, run: Callable[[list[str]], str] = run_command
) -> int:
    """Optimize a single image file losslessly. Return bytes saved (0 on failure/skip)."""
    suffix = image_path.suffix.lower()
    if suffix not in _SUPPORTED_EXTENSIONS:
        return 0

    # Skip optimization if no tool is available (prevents FileNotFoundError)
    if not check_optimizer_available(os.name):
        return 0

    original_size = image_path.stat().st_size

    cmd = _build_command(suffix)

    try:
        run(cmd + [str(image_path)])
    except SubprocessError as exc:
        logger.warning("Optimization failed for %s: %s", image_path.name, exc)
        return 0

    new_size = image_path.stat().st_size
    return original_size - new_size


def _build_command(suffix: str) -> list[str]:
    """Build the optimization command based on platform and file extension."""
    if os.name == "nt":
        return [get_tool_path("pingo"), "-lossless", "-s4"]

    # posix: oxipng for PNG, jpegoptim for JPEG
    if suffix == ".png":
        return [get_tool_path("oxipng"), "-o", "4", "--strip", "safe"]

    return [get_tool_path("jpegoptim"), "--strip-all"]
