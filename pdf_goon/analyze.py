"""PDF inspection: page count, image metadata, page dimensions, and processing decisions."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

from pdf_goon.geometry import extract_page_geometry, is_full_page_image
from pdf_goon.models import (
    DPI_MAX,
    DPI_MIN,
    TRICKY_COLORS,
    ImageInfo,
    PageDecision,
    PageInfo,
    ProcessingMode,
)

logger = logging.getLogger(__name__)


def get_page_count(pdf_path: Path) -> int | None:
    """Return total page count, or None if PDF is unreadable."""
    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            return len(reader.pages)
    except Exception:
        return None


def is_true_pdf_mask(xobj_dict: object) -> bool:
    """Return True if image XObject dictionary specifies a PDF mask according to ISO 32000-1.

    Checks:
    - /ImageMask is True (stencil mask)
    - /SMask is present (soft mask / alpha transparency)
    - /Mask is present (explicit or color-key mask)
    """
    if not isinstance(xobj_dict, Mapping):
        return False
    try:
        if xobj_dict.get("/ImageMask") is True:
            return True
        if "/SMask" in xobj_dict:
            return True
        if "/Mask" in xobj_dict:
            return True
    except Exception:
        return False
    return False


TEXT_SHOW_OPS: set[bytes] = {b"Tj", b"TJ", b"'", b'"'}


def analyze_page_text_layers(page: object, reader: object = None) -> tuple[bool, bool]:
    """Inspect page ContentStream operations for visible and invisible (OCR) text.

    Returns:
        (has_visible_text, has_invisible_ocr_text)
    """
    contents = None
    if hasattr(page, "get_contents"):
        try:
            contents = page.get_contents()
        except Exception:
            contents = None

    if contents is None and hasattr(page, "get"):
        try:
            contents = page.get("/Contents")
        except Exception:
            contents = None

    if contents is not None:
        try:
            from pypdf.generic import ContentStream

            cs = ContentStream(contents, reader)
            current_tr = 0
            has_visible = False
            has_invisible = False

            for args, op in cs.operations:
                if op == b"Tr" and args:
                    try:
                        current_tr = int(args[0])
                    except Exception:
                        current_tr = 0
                elif op in TEXT_SHOW_OPS:
                    if current_tr == 3:
                        has_invisible = True
                    else:
                        has_visible = True

            return has_visible, has_invisible
        except Exception:
            pass

    # Fallback to extract_text() if ContentStream parsing is unavailable or fails
    if hasattr(page, "extract_text"):
        try:
            extracted = page.extract_text()
            if isinstance(extracted, str):
                return bool(extracted.strip()), False
        except Exception:
            pass

    return False, False


def get_image_data(
    pdf_path: Path,
    page_num: int,
) -> tuple[list[ImageInfo], list[str], bool]:
    """Return (images, mask_indices, has_text) for a given page.

    has_text is True when the page contains substantive visible text
    operators (excluding invisible OCR text under 3 Tr).
    """
    images: list[ImageInfo] = []
    mask_indices: list[str] = []
    has_text = False

    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page = reader.pages[page_num - 1]

            # Detect substantive text: distinguish visible text from 3 Tr OCR
            has_visible_text, _ = analyze_page_text_layers(page, reader)
            has_text = has_visible_text

            for img_idx, img_file in enumerate(page.images):
                pil_image = img_file.image
                if pil_image is None:
                    width = 0
                    height = 0
                    color = "unknown"
                else:
                    try:
                        width = pil_image.width
                        height = pil_image.height
                        color = pil_image.mode.lower()
                    except Exception:
                        width = 0
                        height = 0
                        color = "unknown"

                # Check true PDF mask flags (/ImageMask, /SMask, /Mask)
                xobj = None
                if (
                    hasattr(img_file, "indirect_reference")
                    and img_file.indirect_reference is not None
                ):
                    try:
                        xobj = img_file.indirect_reference.get_object()
                    except Exception:
                        xobj = None

                # Check non-standard ColorTransform (0) in image decode params
                if xobj is not None and isinstance(xobj, Mapping):
                    decode_parms = xobj.get("/DecodeParms")
                    if (
                        isinstance(decode_parms, Mapping)
                        and decode_parms.get("/ColorTransform") == 0
                    ):
                        color = "colortransform0"
                    elif xobj.get("/ColorTransform") == 0:
                        color = "colortransform0"

                is_mask = is_true_pdf_mask(xobj)
                if is_mask:
                    mask_indices.append(str(img_idx).zfill(3))
                else:
                    images.append(
                        ImageInfo(
                            width=width,
                            height=height,
                            color=color,
                            is_mask=False,
                        )
                    )
    except Exception as e:
        logger.warning(f"Error parsing images with pypdf: {e}")

    return images, mask_indices, has_text


class PypdfSession:
    """Sequential analysis session holding open reader handles for a single PDF.

    Eliminates redundant file opens and parses across multi-page documents (D7).
    """

    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = pdf_path
        self._f: BinaryIO | None = open(pdf_path, "rb")
        self.reader: Any = None
        self.doc: Any = None
        try:
            import pypdf
            import pypdfium2 as pdfium

            self.reader = pypdf.PdfReader(self._f)
            self.doc = pdfium.PdfDocument(pdf_path)
            self.page_count = len(self.reader.pages)
        except Exception:
            self.close()
            raise

    def inspect_page(
        self, page_num: int
    ) -> tuple[list[ImageInfo], list[str], bool, PageInfo]:
        """Inspect page for text layers, geometry, and image metadata in a single pass."""
        if self.reader is None or self.doc is None:
            raise RuntimeError("PypdfSession is closed or uninitialized")

        page = self.reader.pages[page_num - 1]
        has_visible_text, _ = analyze_page_text_layers(page, self.reader)

        # Query geometry and rotation from pdfium
        try:
            pdfium_page = self.doc[page_num - 1]
            (page_w, page_h), image_bboxes, has_rotation = extract_page_geometry(
                pdfium_page
            )
            pdfium_page.close()
        except Exception as e:
            logger.warning(f"Error querying page geometry for page {page_num}: {e}")
            page_w, page_h = 0.0, 0.0
            image_bboxes = []
            has_rotation = False

        if page_w <= 0.0 or page_h <= 0.0:
            try:
                box = page.mediabox
                page_w, page_h = float(box.width), float(box.height)
            except Exception:
                page_w, page_h = 0.0, 0.0

        page_info = PageInfo(width_pts=page_w, height_pts=page_h)

        images: list[ImageInfo] = []
        mask_indices: list[str] = []
        non_mask_count = 0

        for img_idx, img_file in enumerate(page.images):
            pil_image = img_file.image
            if pil_image is None:
                width, height, color = 0, 0, "unknown"
            else:
                try:
                    width, height = pil_image.width, pil_image.height
                    color = pil_image.mode.lower()
                except Exception:
                    width, height, color = 0, 0, "unknown"

            xobj = None
            if (
                hasattr(img_file, "indirect_reference")
                and img_file.indirect_reference is not None
            ):
                try:
                    xobj = img_file.indirect_reference.get_object()
                except Exception:
                    xobj = None

            if xobj is not None and isinstance(xobj, Mapping):
                decode_parms = xobj.get("/DecodeParms")
                if (
                    isinstance(decode_parms, Mapping)
                    and decode_parms.get("/ColorTransform") == 0
                ):
                    color = "colortransform0"
                elif xobj.get("/ColorTransform") == 0:
                    color = "colortransform0"

            if is_true_pdf_mask(xobj):
                mask_indices.append(str(img_idx).zfill(3))
            else:
                bbox = (
                    image_bboxes[non_mask_count]
                    if non_mask_count < len(image_bboxes)
                    else None
                )
                images.append(
                    ImageInfo(
                        width=width,
                        height=height,
                        color=color,
                        is_mask=False,
                        placed_bbox=bbox,
                        has_rotation=has_rotation,
                    )
                )
                non_mask_count += 1

        return images, mask_indices, has_visible_text, page_info

    def close(self) -> None:
        """Close open file and document handles."""
        if hasattr(self, "doc") and self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
            self.doc = None
        if hasattr(self, "_f") and self._f is not None:
            try:
                self._f.close()
            except Exception:
                pass
            self._f = None

    def __enter__(self) -> PypdfSession:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


def get_page_info(
    pdf_path: Path,
    page_num: int,
) -> PageInfo:
    """Return physical page dimensions in points."""
    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page = reader.pages[page_num - 1]
            box = page.mediabox
            return PageInfo(width_pts=float(box.width), height_pts=float(box.height))
    except Exception:
        return PageInfo(width_pts=0.0, height_pts=0.0)


# Coverage threshold: image must cover at least this fraction of page in both dimensions
EXTRACT_COVERAGE_THRESHOLD = 0.95


def _image_fills_page(
    main_img: ImageInfo,
    page_info: PageInfo,
    min_width: int = 500,
    margin_tolerance: float = 3.0,
) -> bool:
    """Check if a single image truly fills the page using geometry or aspect ratio."""
    return is_full_page_image(
        placed_bbox=main_img.placed_bbox,
        page_size=(page_info.width_pts, page_info.height_pts),
        px_size=(main_img.width, main_img.height),
        min_width=min_width,
        area_threshold=EXTRACT_COVERAGE_THRESHOLD,
        max_margin_pts=margin_tolerance,
    )


def decide_processing_mode(
    images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
    force_render: bool,
    *,
    has_text: bool = False,
    keep_blank: bool = False,
    margin_tolerance: float = 3.0,
) -> PageDecision:
    """Determine whether to extract, render, or skip (blank)."""
    # 1. Force render
    if force_render:
        dpi = _clamp_dpi(float(dpi_text))
        return PageDecision(
            mode=ProcessingMode.RENDER, dpi=dpi, reason="Force render enabled"
        )

    non_mask_images = [img for img in images if not img.is_mask]

    # 2. Blank page (no images, no text)
    if not non_mask_images and not has_text:
        if keep_blank:
            dpi = _clamp_dpi(float(dpi_text))
            return PageDecision(
                mode=ProcessingMode.RENDER,
                dpi=dpi,
                reason="Blank page, rendering due to --keep-blank",
            )
        return PageDecision(
            mode=ProcessingMode.BLANK,
            dpi=0,
            reason="Blank page (no images, no text)",
        )

    # 3. Text only (no images)
    if not non_mask_images and has_text:
        dpi = _clamp_dpi(float(dpi_text))
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason=f"Text-only page, rendering at fallback DPI {dpi_text}",
        )

    # 4. Tricky color space
    tricky_img = next(
        (img for img in non_mask_images if img.color in TRICKY_COLORS), None
    )
    if tricky_img is not None:
        dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason=f"Tricky color space ({tricky_img.color}), rendering",
        )

    # 5. Text + image page
    if has_text and non_mask_images:
        dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason="Text + image page, rendering to preserve layout",
        )

    # 6. Small images only (all below min_width)
    largest_width = max(img.width for img in non_mask_images)
    if largest_width < min_width:
        dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason=f"Small images (max {largest_width}px < {min_width}px), using fallback DPI {dpi_text}",
        )

    # 7. Multiple qualifying images
    if len(non_mask_images) > 1:
        dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
        return PageDecision(
            mode=ProcessingMode.RENDER,
            dpi=dpi,
            reason=f"Multiple images ({len(non_mask_images)}), rendering at computed DPI",
        )

    # 8. Single qualifying image (len(non_mask_images) == 1, not tricky, no text, largest_width >= min_width)
    main_img = non_mask_images[0]
    fills_page = _image_fills_page(
        main_img,
        page_info,
        min_width=min_width,
        margin_tolerance=margin_tolerance,
    )

    if fills_page:
        if main_img.has_rotation:
            dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
            return PageDecision(
                mode=ProcessingMode.RENDER,
                dpi=dpi,
                reason="Image fills page but has rotation, rendering to preserve orientation",
            )
        return PageDecision(
            mode=ProcessingMode.EXTRACT,
            dpi=0,
            reason="Single extractable image filling page",
        )

    # Single image does not fill page
    dpi = compute_render_dpi(non_mask_images, page_info, min_width, dpi_text)
    return PageDecision(
        mode=ProcessingMode.RENDER,
        dpi=dpi,
        reason="Single image does not fill page, rendering to preserve background",
    )


# --- Private & Public DPI helpers ---


def _clamp_dpi(dpi: float) -> float:
    """Clamp DPI to [DPI_MIN, DPI_MAX]."""
    return max(DPI_MIN, min(DPI_MAX, dpi))


def compute_render_dpi(
    images: list[ImageInfo],
    page_info: PageInfo,
    min_width: int,
    dpi_text: int,
) -> float:
    """Calculate the best rendering DPI based on embedded image physical placed dimensions.

    Uses actual placed physical inches as denominator to avoid extreme DPI spikes.
    """
    if not images:
        return _clamp_dpi(float(dpi_text))

    # Filter out decorative icons where both dimensions are < min_width
    qualifying_images = [
        img for img in images if not (img.width < min_width and img.height < min_width)
    ]
    if not qualifying_images:
        return _clamp_dpi(float(dpi_text))

    candidates = []
    for img in qualifying_images:
        if img.placed_bbox is not None:
            xmin, ymin, xmax, ymax = img.placed_bbox
            w_placed = max(1.0, xmax - xmin)
            h_placed = max(1.0, ymax - ymin)
            width_dpi = (img.width * 72.0) / w_placed
            height_dpi = (img.height * 72.0) / h_placed
        else:
            width_dpi = (
                (img.width * 72.0) / page_info.width_pts
                if page_info.width_pts > 0
                else float(dpi_text)
            )
            height_dpi = (
                (img.height * 72.0) / page_info.height_pts
                if page_info.height_pts > 0
                else float(dpi_text)
            )
        candidate_dpi = max(width_dpi, height_dpi)
        logger.debug(
            f"Image {img.width}x{img.height}: width_dpi={width_dpi:.2f}, height_dpi={height_dpi:.2f} -> candidate={candidate_dpi:.2f}"
        )
        candidates.append(candidate_dpi)

    max_candidate = max(candidates)
    final_dpi = max(max_candidate, float(dpi_text))
    logger.debug(f"Selected render DPI: {final_dpi:.2f}")

    return _clamp_dpi(final_dpi)


# Alias for backwards compatibility
_compute_render_dpi = compute_render_dpi


def _build_render_reason(
    images: list[ImageInfo], min_width: int, dpi_text: int, has_text: bool = False
) -> str:
    """Build a human-readable reason string for render mode."""
    if not images:
        if has_text:
            return f"Text-only page, rendering at fallback DPI {dpi_text}"
        return f"No images, using fallback DPI {dpi_text}"

    largest_width = max(img.width for img in images)

    if has_text and len(images) == 1 and largest_width >= min_width:
        return "Text + image page, rendering to preserve layout"

    if largest_width < min_width:
        return f"Small images (max {largest_width}px < {min_width}px), using fallback DPI {dpi_text}"

    if len(images) > 1:
        return f"Multiple images ({len(images)}), rendering at computed DPI"

    # Tricky color or other reason
    main_color = images[0].color if images else "unknown"
    if main_color in TRICKY_COLORS:
        return f"Tricky color space ({main_color}), rendering"

    return "Complex page layout, rendering"
