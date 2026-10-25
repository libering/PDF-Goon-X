"""Data definitions for pdf_goon: dataclasses, enums, constants, exceptions."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# --- Constants ---

VERSION: str = "1.2.0"
DPI_MIN: int = 36
DPI_MAX: int = 2400
MIN_WIDTH_DEFAULT: int = 500
PROGRESS_BAR_LENGTH: int = 20
MAX_RENDER_PIXELS: int = 100_000_000  # 100 megapixels (~400MB RGBA buffer)
MAX_DEFAULT_WORKERS: int = 4
TRICKY_COLORS: frozenset[str] = frozenset({"devn", "cmyk", "sep", "colortransform0"})


# --- Enums ---


class ProcessingMode(Enum):
    """How a page should be processed."""

    EXTRACT = "extract"
    RENDER = "render"
    BLANK = "blank"


# --- Dataclasses ---


@dataclass(frozen=True)
class Config:
    """Validated runtime configuration. Immutable after construction."""

    path: Path
    verbose: bool = False
    replace: bool = False
    optimize: bool = True
    dpi_text: int = 400
    min_width: int = 500
    recursive: bool = False
    force_render: bool = False
    debug: bool = False
    keep_blank: bool = False
    margin_tolerance: float = 3.0
    jobs: int = 1
    tiles: bool = False


@dataclass(frozen=True)
class ImageInfo:
    """Metadata for a single embedded image on a PDF page."""

    width: int
    height: int
    color: str
    is_mask: bool = False
    placed_bbox: tuple[float, float, float, float] | None = None
    has_rotation: bool = False


@dataclass(frozen=True)
class PageInfo:
    """Physical dimensions of a PDF page in points (1/72 inch)."""

    width_pts: float
    height_pts: float


@dataclass(frozen=True)
class PageDecision:
    """The processing decision for a single page."""

    mode: ProcessingMode
    dpi: float
    reason: str


@dataclass
class ProcessResult:
    """Outcome of processing a single PDF file."""

    pdf_path: Path
    success: bool
    pages_processed: int = 0
    error: str | None = None


@dataclass(frozen=True)
class PageResult:
    """Outcome of processing a single PDF page."""

    page_num: int
    mode: ProcessingMode
    files_produced: tuple[Path, ...]  # tuple for frozen dataclass
    error: str | None = None


# --- Exceptions ---


class PdfGoonError(Exception):
    """Base exception for unexpected pdf_goon errors."""


class SubprocessError(PdfGoonError):
    """A subprocess exited with non-zero status unexpectedly."""

    def __init__(self, tool: str, exit_code: int, stderr: str) -> None:
        self.tool = tool
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(f"{tool} exited with code {exit_code}: {stderr}")


# --- Factory ---


def _clamp_dpi(raw_dpi: object) -> int:
    """Clamp DPI to configured safe bounds [DPI_MIN, DPI_MAX]."""
    dpi = raw_dpi if isinstance(raw_dpi, int) else int(str(raw_dpi or 400))
    if dpi < DPI_MIN:
        warnings.warn(
            f"DPI {dpi} is very low. Clamping to minimum {DPI_MIN}.",
            stacklevel=3,
        )
        return DPI_MIN
    if dpi > DPI_MAX:
        warnings.warn(
            f"DPI {dpi} is extremely high. Clamping to maximum {DPI_MAX}.",
            stacklevel=3,
        )
        return DPI_MAX
    return dpi


def make_config(**kwargs: object) -> Config:
    """Construct a validated Config, clamping DPI and checking path existence."""
    raw_path = kwargs.get("path", ".")
    path = Path(str(raw_path)).resolve()
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")

    dpi_text = _clamp_dpi(kwargs.get("dpi_text", 400))
    debug = bool(kwargs.get("debug", False))
    verbose = bool(kwargs.get("verbose", False)) or debug

    raw_min_w = kwargs.get("min_width", MIN_WIDTH_DEFAULT)
    min_width_val = raw_min_w if isinstance(raw_min_w, int) else int(str(raw_min_w))

    raw_margin = kwargs.get("margin_tolerance", 3.0)
    margin_tolerance_val = float(raw_margin) if raw_margin is not None else 3.0  # type: ignore[arg-type]

    raw_jobs = kwargs.get("jobs", 1)
    jobs_val = max(0, int(str(raw_jobs if raw_jobs is not None else 1)))

    return Config(
        path=path,
        verbose=verbose,
        replace=bool(kwargs.get("replace", False)),
        optimize=bool(kwargs.get("optimize", True)),
        dpi_text=dpi_text,
        min_width=min_width_val,
        recursive=bool(kwargs.get("recursive", False)),
        force_render=bool(kwargs.get("force_render", False)),
        debug=debug,
        keep_blank=bool(kwargs.get("keep_blank", False)),
        margin_tolerance=margin_tolerance_val,
        jobs=jobs_val,
        tiles=bool(kwargs.get("tiles", False)),
    )
