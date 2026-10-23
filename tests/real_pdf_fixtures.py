"""Real PDF fixtures for integration and end-to-end testing.

Generates structurally valid, authentic ISO 32000 PDF files covering:
- Full page scanned manga (RGB JPEG)
- Scanned manga with 1.5pt white border (D1 fix verification)
- Scanned manga with 15pt large white margin (non-full-page render trigger)
- Scanned book with invisible OCR text layer (3 Tr, D2 fix verification)
- Page with visible typography and embedded image (mixed content render trigger)
- Scanned 1-bit monochrome novel page (D3 fix verification, no mask)
- Multi-image layout page (render trigger)
- Pure text page (render at fallback DPI)
- Blank page (BLANK mode)
- Multi-page mixed book (testing session and batch worker)
"""

from __future__ import annotations

import io
from pathlib import Path
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

from tests.fixtures_books import (
    make_light_novel_complete_volume_pdf,
    make_multi_page_mixed_book_pdf,
    make_novel_with_chapter_ornament_pdf,
    make_pure_text_novel_pdf,
)

__all__ = [
    'make_blank_pdf',
    'make_form_xobject_text_pdf',
    'make_full_page_manga_pdf',
    'make_image_with_smask_pdf',
    'make_large_margin_15pt_pdf',
    'make_light_novel_complete_volume_pdf',
    'make_monochrome_1bit_pdf',
    'make_multi_images_pdf',
    'make_multi_page_mixed_book_pdf',
    'make_novel_with_chapter_ornament_pdf',
    'make_ocr_invisible_text_pdf',
    'make_pure_text_novel_pdf',
    'make_pure_text_pdf',
    'make_visible_text_pdf',
    'make_white_border_1_5pt_pdf',
]



def _make_jpeg_bytes(
    width: int = 1200, height: int = 1600, color: tuple[int, int, int] = (220, 80, 80)
) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _make_1bit_bytes(width: int = 1200, height: int = 1600) -> bytes:
    # 1-bit monochrome image (mode '1')
    img = Image.new("1", (width, height), color=0)
    # Draw some white pattern
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            img.putpixel((x, y), 1)
    # Return raw uncompressed 1-bit bitmap bytes
    # Each row is padded to byte boundary
    row_bytes = (width + 7) // 8
    raw_data = bytearray(row_bytes * height)
    for y in range(height):
        for x in range(width):
            if img.getpixel((x, y)):
                byte_idx = y * row_bytes + (x // 8)
                bit_idx = 7 - (x % 8)
                raw_data[byte_idx] |= 1 << bit_idx
    import zlib

    return zlib.compress(bytes(raw_data))


def _add_standard_font(writer: PdfWriter) -> IndirectObject:
    font_dict = DictionaryObject()
    font_dict[NameObject("/Type")] = NameObject("/Font")
    font_dict[NameObject("/Subtype")] = NameObject("/Type1")
    font_dict[NameObject("/BaseFont")] = NameObject("/Helvetica")
    return writer._add_object(font_dict)


def make_full_page_manga_pdf(path: Path) -> Path:
    """Page: 600x800 pt, Image: 1200x1600 px placed at (0, 0, 600, 800)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    jpg_bytes = _make_jpeg_bytes(1200, 1600, (180, 40, 40))

    img_obj = DecodedStreamObject()
    img_obj.set_data(jpg_bytes)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(1200)
    img_obj[NameObject("/Height")] = NumberObject(1600)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    img_ref = writer._add_object(img_obj)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = img_ref
    res[NameObject("/XObject")] = xobjs
    page[NameObject("/Resources")] = res

    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_white_border_1_5pt_pdf(path: Path) -> Path:
    """Page: 603x803 pt, Image: 1200x1600 px placed at (1.5, 1.5, 600, 800).

    Margin is 1.5pt <= 3.0pt tolerance. Coverage = 99.0% >= 95%.
    Must be decided as EXTRACT (D1 bugfix).
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=603, height=803)
    jpg_bytes = _make_jpeg_bytes(1200, 1600, (40, 140, 180))

    img_obj = DecodedStreamObject()
    img_obj.set_data(jpg_bytes)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(1200)
    img_obj[NameObject("/Height")] = NumberObject(1600)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    img_ref = writer._add_object(img_obj)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = img_ref
    res[NameObject("/XObject")] = xobjs
    page[NameObject("/Resources")] = res

    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 1.5 1.5 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_large_margin_15pt_pdf(path: Path) -> Path:
    """Page: 630x830 pt, Image: 1200x1600 px placed at (15, 15, 600, 800).

    Margin is 15pt > 3.0pt tolerance. Coverage = 91.8% < 95%.
    Must be decided as RENDER to preserve page composition.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=630, height=830)
    jpg_bytes = _make_jpeg_bytes(1200, 1600, (40, 180, 40))

    img_obj = DecodedStreamObject()
    img_obj.set_data(jpg_bytes)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(1200)
    img_obj[NameObject("/Height")] = NumberObject(1600)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    img_ref = writer._add_object(img_obj)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = img_ref
    res[NameObject("/XObject")] = xobjs
    page[NameObject("/Resources")] = res

    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 15 15 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_ocr_invisible_text_pdf(path: Path) -> Path:
    """Full-page image + invisible OCR text (3 Tr).

    Must be decided as EXTRACT (D2 bugfix).
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    jpg_bytes = _make_jpeg_bytes(1200, 1600, (180, 100, 200))

    img_obj = DecodedStreamObject()
    img_obj.set_data(jpg_bytes)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(1200)
    img_obj[NameObject("/Height")] = NumberObject(1600)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    img_ref = writer._add_object(img_obj)
    font_ref = _add_standard_font(writer)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = img_ref
    res[NameObject("/XObject")] = xobjs
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    res[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = res

    # Stream has image and 3 Tr text operator
    cs = DecodedStreamObject()
    cs.set_data(
        b"q 600 0 0 800 0 0 cm /Im0 Do Q BT /F1 12 Tf 3 Tr 100 700 Td (Invisible OCR Layer Text) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_visible_text_pdf(path: Path) -> Path:
    """Full-page image + visible typography (0 Tr).

    Must be decided as RENDER (mixed content).
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    jpg_bytes = _make_jpeg_bytes(1200, 1600, (220, 140, 40))

    img_obj = DecodedStreamObject()
    img_obj.set_data(jpg_bytes)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(1200)
    img_obj[NameObject("/Height")] = NumberObject(1600)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    img_ref = writer._add_object(img_obj)
    font_ref = _add_standard_font(writer)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = img_ref
    res[NameObject("/XObject")] = xobjs
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    res[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = res

    cs = DecodedStreamObject()
    cs.set_data(
        b"q 600 0 0 800 0 0 cm /Im0 Do Q BT /F1 18 Tf 0 Tr 50 720 Td (Visible Chapter Title) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_monochrome_1bit_pdf(path: Path) -> Path:
    """1-bit monochrome scanned novel/manga page (no mask flag).

    Must be decided as EXTRACT (D3 bugfix, no silent data loss).
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    flate_bytes = _make_1bit_bytes(1200, 1600)

    img_obj = DecodedStreamObject()
    img_obj.set_data(flate_bytes)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(1200)
    img_obj[NameObject("/Height")] = NumberObject(1600)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceGray")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(1)
    img_obj[NameObject("/Filter")] = NameObject("/FlateDecode")
    img_ref = writer._add_object(img_obj)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = img_ref
    res[NameObject("/XObject")] = xobjs
    page[NameObject("/Resources")] = res

    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_multi_images_pdf(path: Path) -> Path:
    """Page with 2 distinct images placed side-by-side."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    jpg1 = _make_jpeg_bytes(600, 800, (200, 50, 50))
    jpg2 = _make_jpeg_bytes(600, 800, (50, 50, 200))

    def _create_img(data: bytes) -> IndirectObject:
        obj = DecodedStreamObject()
        obj.set_data(data)
        obj[NameObject("/Type")] = NameObject("/XObject")
        obj[NameObject("/Subtype")] = NameObject("/Image")
        obj[NameObject("/Width")] = NumberObject(600)
        obj[NameObject("/Height")] = NumberObject(800)
        obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
        obj[NameObject("/BitsPerComponent")] = NumberObject(8)
        obj[NameObject("/Filter")] = NameObject("/DCTDecode")
        return writer._add_object(obj)

    ref1 = _create_img(jpg1)
    ref2 = _create_img(jpg2)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = ref1
    xobjs[NameObject("/Im1")] = ref2
    res[NameObject("/XObject")] = xobjs
    page[NameObject("/Resources")] = res

    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 400 0 400 cm /Im0 Do Q q 600 0 0 400 0 0 cm /Im1 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_pure_text_pdf(path: Path) -> Path:
    """Page with pure text, no images."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font_ref = _add_standard_font(writer)

    res = DictionaryObject()
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    res[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = res

    cs = DecodedStreamObject()
    cs.set_data(b"BT /F1 14 Tf 50 700 Td (Pure text page content) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_blank_pdf(path: Path) -> Path:
    """Blank page without content."""
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_image_with_smask_pdf(path: Path) -> Path:
    """Page with an image that has an attached /SMask (soft mask for transparency).

    Must be decided as EXTRACT (full-page image), NEVER BLANK!
    Verifies regression fix where /SMask presence incorrectly marked image as mask.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    jpg_bytes = _make_jpeg_bytes(1200, 1600)
    smask_bytes = _make_1bit_bytes(1200, 1600)

    # Auxiliary SMask object
    smask_obj = DecodedStreamObject()
    smask_obj.set_data(smask_bytes)
    smask_obj[NameObject("/Type")] = NameObject("/XObject")
    smask_obj[NameObject("/Subtype")] = NameObject("/Image")
    smask_obj[NameObject("/Width")] = NumberObject(1200)
    smask_obj[NameObject("/Height")] = NumberObject(1600)
    smask_obj[NameObject("/ColorSpace")] = NameObject("/DeviceGray")
    smask_obj[NameObject("/BitsPerComponent")] = NumberObject(1)
    smask_obj[NameObject("/Filter")] = NameObject("/FlateDecode")
    smask_ref = writer._add_object(smask_obj)

    # Parent image with /SMask
    img_obj = DecodedStreamObject()
    img_obj.set_data(jpg_bytes)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(1200)
    img_obj[NameObject("/Height")] = NumberObject(1600)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    img_obj[NameObject("/SMask")] = smask_ref
    img_ref = writer._add_object(img_obj)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = img_ref
    res[NameObject("/XObject")] = xobjs
    page[NameObject("/Resources")] = res

    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_form_xobject_text_pdf(path: Path) -> Path:
    """Page with text nested inside a Form XObject invoked via 'Do'.

    Must be decided as RENDER (text-only page), NEVER BLANK!
    Verifies regression fix where nested Form XObjects were ignored by ContentStream analysis.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)

    # Form XObject stream
    form_obj = DecodedStreamObject()
    form_obj.set_data(b"BT /F1 12 Tf 50 700 Td (Novel text inside Form XObject) Tj ET")
    form_obj[NameObject("/Type")] = NameObject("/XObject")
    form_obj[NameObject("/Subtype")] = NameObject("/Form")
    form_obj[NameObject("/BBox")] = ArrayObject(
        [FloatObject(0), FloatObject(0), FloatObject(600), FloatObject(800)]
    )

    form_res = DictionaryObject()
    form_fonts = DictionaryObject()
    f1 = DictionaryObject()
    f1[NameObject("/Type")] = NameObject("/Font")
    f1[NameObject("/Subtype")] = NameObject("/Type1")
    f1[NameObject("/BaseFont")] = NameObject("/Helvetica")
    form_fonts[NameObject("/F1")] = f1
    form_res[NameObject("/Font")] = form_fonts
    form_obj[NameObject("/Resources")] = form_res

    form_ref = writer._add_object(form_obj)

    # Page resources referencing the Form XObject
    page_res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Xf1")] = form_ref
    page_res[NameObject("/XObject")] = xobjs
    page[NameObject("/Resources")] = page_res

    # Page content stream invokes /Xf1 via Do
    cs = DecodedStreamObject()
    cs.set_data(b"q /Xf1 Do Q")
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


