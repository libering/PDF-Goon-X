"""Synthetic edge-case PDF generators for engine boundary and invariant testing.

Covers the 5 critical boundary corpus types (handoverbook.md §5):
1. Two-Page Spread (橫向跨頁大圖): Aspect ratio ~1.5 (e.g. 1200x800 pt, 2400x1600 px image).
2. Bleed Margins (CropBox != MediaBox): Commercial print bleed margins.
3. Rotation Labels (/Rotate 90/270): Page rotation tag with upright embedded image.
4. Monochrome Bitmaps (1-bit scan): Pure 1-bit scan without mask.
5. Vector/Text Overlay: Full-bleed background image with Form XObject text overlay.
"""

from __future__ import annotations

import io
from pathlib import Path
import zlib
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NumberObject,
)


def _make_jpeg_bytes(
    width: int = 1200,
    height: int = 1600,
    color: tuple[int, int, int] = (200, 80, 80),
) -> bytes:
    """Generate JPEG image byte stream."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _make_1bit_compressed_bytes(width: int = 1200, height: int = 1600) -> bytes:
    """Generate 1-bit monochrome image byte stream compressed with Flate."""
    row_bytes = (width + 7) // 8
    raw_data = bytearray(row_bytes * height)
    # Draw simple diagonal stripes
    for y in range(height):
        for x in range(0, width, 8):
            if ((x + y) // 8) % 2 == 0:
                raw_data[y * row_bytes + (x // 8)] |= 0xAA
    return zlib.compress(bytes(raw_data))


def _add_image_xobject(
    writer: PdfWriter,
    data: bytes,
    width: int,
    height: int,
    color_space: str = "/DeviceRGB",
    bpc: int = 8,
    filter_name: str = "/DCTDecode",
) -> IndirectObject:
    """Register an image XObject in the PDF writer."""
    img_obj = DecodedStreamObject()
    img_obj.set_data(data)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(width)
    img_obj[NameObject("/Height")] = NumberObject(height)
    img_obj[NameObject("/ColorSpace")] = NameObject(color_space)
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(bpc)
    img_obj[NameObject("/Filter")] = NameObject(filter_name)
    return writer._add_object(img_obj)


def _add_form_text_xobject(
    writer: PdfWriter,
    text: str,
    bbox: tuple[float, float, float, float] = (0, 0, 600, 800),
) -> IndirectObject:
    """Register a Form XObject with embedded typography in the PDF writer."""
    f1 = DictionaryObject()
    f1[NameObject("/Type")] = NameObject("/Font")
    f1[NameObject("/Subtype")] = NameObject("/Type1")
    f1[NameObject("/BaseFont")] = NameObject("/Helvetica")

    form_res = DictionaryObject()
    form_res[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): f1})

    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 14 Tf 50 700 Td ({text}) Tj ET".encode("ascii"))
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Form")
    stream[NameObject("/BBox")] = ArrayObject([FloatObject(v) for v in bbox])
    stream[NameObject("/Resources")] = form_res
    return writer._add_object(stream)


def make_two_page_spread_pdf(path: Path) -> Path:
    """Generate wide landscape page (1200x800 pt) with full-bleed 2400x1600 px image."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=1200, height=800)
    img_ref = _add_image_xobject(writer, _make_jpeg_bytes(2400, 1600), 2400, 1600)

    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): img_ref})}
    )
    cs = DecodedStreamObject()
    cs.set_data(b"q 1200 0 0 800 0 0 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_bleed_margins_pdf(path: Path, bleed_pts: float = 10.0) -> Path:
    """Generate page with MediaBox (620x820 pt) and CropBox (600x800 pt)."""
    writer = PdfWriter()
    w_media, h_media = 600 + 2 * bleed_pts, 800 + 2 * bleed_pts
    page = writer.add_blank_page(width=w_media, height=h_media)
    page[NameObject("/CropBox")] = ArrayObject(
        [
            FloatObject(bleed_pts),
            FloatObject(bleed_pts),
            FloatObject(600 + bleed_pts),
            FloatObject(800 + bleed_pts),
        ]
    )

    img_ref = _add_image_xobject(writer, _make_jpeg_bytes(1240, 1640), 1240, 1640)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): img_ref})}
    )
    cs = DecodedStreamObject()
    cs.set_data(f"q {w_media} 0 0 {h_media} 0 0 cm /Im0 Do Q".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_rotated_page_pdf(path: Path, rotation: int = 90) -> Path:
    """Generate page with /Rotate tag and unrotated raw image."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    page[NameObject("/Rotate")] = NumberObject(rotation)

    img_ref = _add_image_xobject(writer, _make_jpeg_bytes(1200, 1600), 1200, 1600)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): img_ref})}
    )
    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_monochrome_1bit_pdf(path: Path) -> Path:
    """Generate page with 1-bit monochrome image (/BitsPerComponent 1, no mask)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    raw_1bit = _make_1bit_compressed_bytes(1200, 1600)
    img_ref = _add_image_xobject(
        writer,
        raw_1bit,
        1200,
        1600,
        color_space="/DeviceGray",
        bpc=1,
        filter_name="/FlateDecode",
    )

    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): img_ref})}
    )
    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_vector_overlay_pdf(path: Path) -> Path:
    """Generate page with full-bleed background image and Form XObject typography overlay."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    img_ref = _add_image_xobject(writer, _make_jpeg_bytes(1200, 1600), 1200, 1600)
    form_ref = _add_form_text_xobject(
        writer, "Scanlation Watermark / Retouch", (0, 0, 600, 800)
    )

    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Im0"): img_ref, NameObject("/Fm0"): form_ref}
            )
        }
    )
    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q q /Fm0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path
