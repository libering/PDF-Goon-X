"""Finalization of rendered and extracted image files."""

from __future__ import annotations

import logging
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from pdf_goon.models import Config
from pdf_goon.optimize import optimize_image as _default_optimize_image

logger = logging.getLogger(__name__)


def _resolve_optimizer() -> Callable[[Path], int]:
    """Dynamically resolve optimize_image hook from pdf_goon.core if patched."""
    core = sys.modules.get("pdf_goon.core")
    return getattr(core, "optimize_image", _default_optimize_image) if core else _default_optimize_image


def _finalize_rendered_file(
    generated_files: list[Path],
    page: int,
    output_dir: Path,
    config: Config,
) -> list[Path]:
    """RENDER path: optimize → rename with _r suffix → move to output."""
    output_files: list[Path] = []
    opt_fn = _resolve_optimizer()

    for local_file in generated_files:
        suffix = local_file.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg"):
            continue

        if config.optimize:
            opt_fn(local_file)

        dest_name = f"{page:03d}_r{suffix}"
        dest_path = output_dir / dest_name
        shutil.move(str(local_file), str(dest_path))
        output_files.append(dest_path)

    return output_files


def _get_extracted_dest_path(
    output_dir: Path, page: int, suffix: str, local_name: str
) -> Path:
    """Determine destination path for extracted file, handling sub-images."""
    dest_name = f"{page:03d}{suffix}"
    dest_path = output_dir / dest_name
    if dest_path.exists():
        sub_idx = re.search(r"-(\d+)\.[^.]+$", local_name)
        if sub_idx:
            dest_name = f"{page:03d}_{sub_idx.group(1)}{suffix}"
            dest_path = output_dir / dest_name
    return dest_path


def _finalize_extracted_files(
    generated_files: list[Path],
    mask_indices: list[str],
    page: int,
    output_dir: Path,
    config: Config,
) -> list[Path]:
    """EXTRACT path: filter masks → optimize → rename with page number → move."""
    output_files: list[Path] = []
    opt_fn = _resolve_optimizer()

    for local_file in generated_files:
        match = re.search(r"-(\d+)\.(?:png|jpg|jpeg)$", local_file.name, re.IGNORECASE)
        if not match:
            continue

        file_idx_str = match.group(1)
        if file_idx_str.zfill(3) in mask_indices:
            logger.debug("      Deleting mask: %s", local_file.name)
            local_file.unlink()
            continue

        suffix = local_file.suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg"):
            continue

        if config.optimize:
            opt_fn(local_file)

        dest_path = _get_extracted_dest_path(
            output_dir, page, suffix, local_file.name
        )
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
