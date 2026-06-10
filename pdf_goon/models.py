"""Data definitions for pdf_goon: dataclasses, enums, constants, exceptions."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# --- Constants ---

VERSION: str = "1.0"
DPI_MIN: int = 36
DPI_MAX: int = 2400
MIN_WIDTH_DEFAULT: int = 500
PROGRESS_BAR_LENGTH: int = 20
TRICKY_COLORS: frozenset[str] = frozenset({"devn", "cmyk", "sep"})
POPPLER_TOOLS: tuple[str, ...] = ("pdfimages", "pdfinfo", "pdftocairo")


# --- Enums ---


class ProcessingMode(Enum):
    """How a page should be processed."""

    EXTRACT = "extract"
    RENDER = "render"


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


@dataclass(frozen=True)
class ImageInfo:
    """Metadata for a single embedded image on a PDF page."""

    width: int
    height: int
    color: str
    is_mask: bool


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


class ToolNotFoundError(PdfGoonError):
    """Required Poppler tool is missing from the system."""

    def __init__(self, missing_tools: list[str]) -> None:
        self.missing_tools = missing_tools
        super().__init__(
            f"Missing required tools: {', '.join(missing_tools)}"
        )


class SubprocessError(PdfGoonError):
    """A subprocess exited with non-zero status unexpectedly."""

    def __init__(self, tool: str, exit_code: int, stderr: str) -> None:
        self.tool = tool
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(
            f"{tool} exited with code {exit_code}: {stderr}"
        )


# --- Factory ---


def make_config(**kwargs: object) -> Config:
    """Construct a validated Config, clamping DPI and checking path existence."""
    # Resolve path
    raw_path = kwargs.get("path", ".")
    path = Path(str(raw_path)).resolve()
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")

    # Clamp dpi_text
    raw_dpi = kwargs.get("dpi_text", 400)
    dpi_text = raw_dpi if isinstance(raw_dpi, int) else int(str(raw_dpi))
    if dpi_text < DPI_MIN:
        warnings.warn(
            f"DPI {dpi_text} is very low. Clamping to minimum {DPI_MIN}.",
            stacklevel=2,
        )
        dpi_text = DPI_MIN
    elif dpi_text > DPI_MAX:
        warnings.warn(
            f"DPI {dpi_text} is extremely high. Clamping to maximum {DPI_MAX}.",
            stacklevel=2,
        )
        dpi_text = DPI_MAX

    # debug implies verbose
    debug = bool(kwargs.get("debug", False))
    verbose = bool(kwargs.get("verbose", False)) or debug

    raw_min_w = kwargs.get("min_width", MIN_WIDTH_DEFAULT)
    min_width_val = raw_min_w if isinstance(raw_min_w, int) else int(str(raw_min_w))

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
    )
