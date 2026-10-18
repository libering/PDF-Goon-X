"""Image metadata extraction and mask identification."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from pdf_goon.analyze.text import analyze_page_text_layers
from pdf_goon.models import ImageInfo, PageInfo

logger = logging.getLogger(__name__)


def is_true_pdf_mask(xobj_dict: object) -> bool:
    """Return True if image XObject dictionary specifies a stencil mask according to ISO 32000-1.

    Checks:
    - /ImageMask is True (1-bit stencil mask)

    Note:
    - /SMask and /Mask indicate attached transparency masks on a parent image;
      the parent image itself is NOT a mask and must not be discarded.
    """
    if not isinstance(xobj_dict, Mapping):
        return False
    try:
        if xobj_dict.get("/ImageMask") is True:
            return True
    except Exception:
        return False
    return False


def get_page_count(pdf_path: Path) -> int | None:
    """Return total page count, or None if PDF is unreadable."""
    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            return len(reader.pages)
    except Exception:
        return None


def get_page_info(pdf_path: Path, page_num: int) -> PageInfo:
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


def _extract_image_entry(
    img_file: object, img_idx: int
) -> tuple[ImageInfo | None, str | None]:
    """Extract ImageInfo and detect stencil mask for a single page image."""
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

    if is_true_pdf_mask(xobj):
        return None, str(img_idx).zfill(3)

    return (
        ImageInfo(width=width, height=height, color=color, is_mask=False),
        None,
    )


def get_image_data(
    pdf_path: Path,
    page_num: int,
) -> tuple[list[ImageInfo], list[str], bool]:
    """Return (images, mask_indices, has_text) for a given page."""
    images: list[ImageInfo] = []
    mask_indices: list[str] = []
    has_text = False

    try:
        import pypdf

        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page = reader.pages[page_num - 1]
            has_visible_text, _ = analyze_page_text_layers(page, reader)
            has_text = has_visible_text

            for img_idx, img_file in enumerate(page.images):
                img_info, mask_idx = _extract_image_entry(img_file, img_idx)
                if mask_idx is not None:
                    mask_indices.append(mask_idx)
                elif img_info is not None:
                    images.append(img_info)
    except Exception as e:
        logger.warning(f"Error parsing images with pypdf: {e}")

    return images, mask_indices, has_text
