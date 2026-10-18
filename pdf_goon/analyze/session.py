"""Sequential analysis session holding open reader handles for a single PDF."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO

from pdf_goon.analyze.image import is_true_pdf_mask
from pdf_goon.analyze.text import analyze_page_text_layers
from pdf_goon.geometry import extract_page_geometry
from pdf_goon.models import ImageInfo, PageInfo

logger = logging.getLogger(__name__)


def _extract_xobj_metadata(img_file: object) -> tuple[int, int, str, object]:
    """Extract dimensions, color mode, and xobject mapping from an image file."""
    pil_image = getattr(img_file, "image", None)
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

    return width, height, color, xobj


class PypdfSession:
    """Sequential analysis session holding open reader handles for a single PDF."""

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

    def _extract_geometry_info(
        self, page_num: int, page: object
    ) -> tuple[PageInfo, list[Any], bool]:
        """Extract page dimension, image bboxes, and rotation status."""
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

        return PageInfo(width_pts=page_w, height_pts=page_h), image_bboxes, has_rotation

    def _extract_page_images(
        self, page: object, image_bboxes: list[Any], has_rotation: bool
    ) -> tuple[list[ImageInfo], list[str]]:
        """Extract ImageInfo list and mask indices from page.images."""
        images: list[ImageInfo] = []
        mask_indices: list[str] = []
        non_mask_count = 0

        for img_idx, img_file in enumerate(page.images):
            width, height, color, xobj = _extract_xobj_metadata(img_file)
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

        return images, mask_indices

    def inspect_page(
        self, page_num: int
    ) -> tuple[list[ImageInfo], list[str], bool, PageInfo]:
        """Inspect page for text layers, geometry, and image metadata in a single pass."""
        if self.reader is None or self.doc is None:
            raise RuntimeError("PypdfSession is closed or uninitialized")

        page = self.reader.pages[page_num - 1]
        has_visible_text, _ = analyze_page_text_layers(page, self.reader)
        page_info, image_bboxes, has_rotation = self._extract_geometry_info(
            page_num, page
        )
        images, mask_indices = self._extract_page_images(
            page, image_bboxes, has_rotation
        )
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
