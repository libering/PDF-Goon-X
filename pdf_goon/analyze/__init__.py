"""PDF inspection: page count, image metadata, page dimensions, and processing decisions."""

from __future__ import annotations

from pdf_goon.analyze.decide import (
    EXTRACT_COVERAGE_THRESHOLD,
    _build_render_reason,
    _clamp_dpi,
    _compute_render_dpi,
    _image_fills_page,
    compute_render_dpi,
    decide_processing_mode,
)
from pdf_goon.analyze.image import (
    get_image_data,
    get_page_count,
    get_page_info,
    is_true_pdf_mask,
)
from pdf_goon.analyze.session import PypdfSession
from pdf_goon.analyze.text import (
    TEXT_SHOW_OPS,
    analyze_page_text_layers,
)

__all__ = [
    "EXTRACT_COVERAGE_THRESHOLD",
    "PypdfSession",
    "TEXT_SHOW_OPS",
    "_build_render_reason",
    "_clamp_dpi",
    "_compute_render_dpi",
    "_image_fills_page",
    "analyze_page_text_layers",
    "compute_render_dpi",
    "decide_processing_mode",
    "get_image_data",
    "get_page_count",
    "get_page_info",
    "is_true_pdf_mask",
]
