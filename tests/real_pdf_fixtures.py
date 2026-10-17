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


def make_multi_page_mixed_book_pdf(path: Path) -> Path:
    """5-page realistic mixed book:

    Page 1: Manga Cover (Full Page RGB) -> EXTRACT
    Page 2: Title & Copyright (Visible Typography) -> RENDER
    Page 3: Scanned Novel Text (1-bit Monochrome) -> EXTRACT
    Page 4: Scanned Page with Invisible OCR (3 Tr) -> EXTRACT
    Page 5: Blank End Page -> BLANK
    """
    writer = PdfWriter()
    font_ref = _add_standard_font(writer)

    # --- Page 1: Manga Cover ---
    p1 = writer.add_blank_page(width=600, height=800)
    jpg1 = _make_jpeg_bytes(1200, 1600, (230, 70, 70))
    img1 = DecodedStreamObject()
    img1.set_data(jpg1)
    img1[NameObject("/Type")] = NameObject("/XObject")
    img1[NameObject("/Subtype")] = NameObject("/Image")
    img1[NameObject("/Width")] = NumberObject(1200)
    img1[NameObject("/Height")] = NumberObject(1600)
    img1[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img1[NameObject("/BitsPerComponent")] = NumberObject(8)
    img1[NameObject("/Filter")] = NameObject("/DCTDecode")
    ref1 = writer._add_object(img1)
    r1 = DictionaryObject()
    x1 = DictionaryObject()
    x1[NameObject("/Im0")] = ref1
    r1[NameObject("/XObject")] = x1
    p1[NameObject("/Resources")] = r1
    c1 = DecodedStreamObject()
    c1.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    p1[NameObject("/Contents")] = writer._add_object(c1)

    # --- Page 2: Title & Copyright (Visible text) ---
    p2 = writer.add_blank_page(width=600, height=800)
    r2 = DictionaryObject()
    f2 = DictionaryObject()
    f2[NameObject("/F1")] = font_ref
    r2[NameObject("/Font")] = f2
    p2[NameObject("/Resources")] = r2
    c2 = DecodedStreamObject()
    c2.set_data(
        b"BT /F1 20 Tf 0 Tr 50 700 Td (PDF-Goon The Adventure) Tj /F1 12 Tf 0 Tr 50 650 Td (Copyright 2026) Tj ET"
    )
    p2[NameObject("/Contents")] = writer._add_object(c2)

    # --- Page 3: 1-bit line art / novel text ---
    p3 = writer.add_blank_page(width=600, height=800)
    b3 = _make_1bit_bytes(1200, 1600)
    img3 = DecodedStreamObject()
    img3.set_data(b3)
    img3[NameObject("/Type")] = NameObject("/XObject")
    img3[NameObject("/Subtype")] = NameObject("/Image")
    img3[NameObject("/Width")] = NumberObject(1200)
    img3[NameObject("/Height")] = NumberObject(1600)
    img3[NameObject("/ColorSpace")] = NameObject("/DeviceGray")
    img3[NameObject("/BitsPerComponent")] = NumberObject(1)
    img3[NameObject("/Filter")] = NameObject("/FlateDecode")
    ref3 = writer._add_object(img3)
    r3 = DictionaryObject()
    x3 = DictionaryObject()
    x3[NameObject("/Im0")] = ref3
    r3[NameObject("/XObject")] = x3
    p3[NameObject("/Resources")] = r3
    c3 = DecodedStreamObject()
    c3.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    p3[NameObject("/Contents")] = writer._add_object(c3)

    # --- Page 4: Scanned Page with Invisible OCR (3 Tr) ---
    p4 = writer.add_blank_page(width=600, height=800)
    jpg4 = _make_jpeg_bytes(1200, 1600, (70, 70, 230))
    img4 = DecodedStreamObject()
    img4.set_data(jpg4)
    img4[NameObject("/Type")] = NameObject("/XObject")
    img4[NameObject("/Subtype")] = NameObject("/Image")
    img4[NameObject("/Width")] = NumberObject(1200)
    img4[NameObject("/Height")] = NumberObject(1600)
    img4[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img4[NameObject("/BitsPerComponent")] = NumberObject(8)
    img4[NameObject("/Filter")] = NameObject("/DCTDecode")
    ref4 = writer._add_object(img4)
    r4 = DictionaryObject()
    x4 = DictionaryObject()
    x4[NameObject("/Im0")] = ref4
    r4[NameObject("/XObject")] = x4
    f4 = DictionaryObject()
    f4[NameObject("/F1")] = font_ref
    r4[NameObject("/Font")] = f4
    p4[NameObject("/Resources")] = r4
    c4 = DecodedStreamObject()
    c4.set_data(
        b"q 600 0 0 800 0 0 cm /Im0 Do Q BT /F1 12 Tf 3 Tr 100 700 Td (Invisible OCR Text On Scanned Page) Tj ET"
    )
    p4[NameObject("/Contents")] = writer._add_object(c4)

    # --- Page 5: Blank End Page ---
    writer.add_blank_page(width=600, height=800)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_pure_text_novel_pdf(path: Path, num_pages: int = 10) -> Path:
    """Generate an authentic multi-page pure text novel (A5 format, 420x595 pt).

    Each page contains running header, chapter headings, body paragraphs, and
    page numbers. Has NO images. Tests multi-page text novel continuous rendering.
    """
    writer = PdfWriter()
    font_ref = _add_standard_font(writer)

    sample_paragraphs = [
        "The Time Traveller was expounding a recondite matter to us.",
        "His grey eyes shone and twinkled, and his usually pale face was flushed.",
        "The fire burned brightly, and the soft radiance of the incandescent",
        "lights in the lilies of silver caught the bubbles that flashed and",
        "passed in our glasses. Our chairs, being his patents, embraced and",
        "caressed us rather than submitted to be sat upon; and there was that",
        "luxurious after-dinner atmosphere when thought runs gracefully free.",
        "It was at this moment that he began his singular demonstration.",
        "Drawing a small crystal mechanism from his pocket, he placed it carefully",
        "upon the mahogany table beneath the glow of the reading lamp.",
        "We watched him with that amused skepticism characteristic of men of science.",
        "He paused, smiled, and turned the bronze lever with a deliberate motion.",
    ]

    for p_idx in range(1, num_pages + 1):
        page = writer.add_blank_page(width=420, height=595)
        res = DictionaryObject()
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = font_ref
        res[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = res

        lines = [
            f"BT /F1 9 Tf 0 Tr 50 560 Td (THE TIME MACHINE - CHAPTER {((p_idx - 1) // 3) + 1}) Tj ET".encode(
                "ascii"
            ),
        ]
        if p_idx == 1 or p_idx % 3 == 1:
            lines.append(
                f"BT /F1 15 Tf 0 Tr 50 520 Td (Chapter {((p_idx - 1) // 3) + 1}) Tj ET".encode(
                    "ascii"
                )
            )
            y_start = 480
        else:
            y_start = 520

        for idx, text in enumerate(sample_paragraphs):
            y_pos = y_start - (idx * 24)
            if y_pos < 80:
                break
            lines.append(
                f"BT /F1 10 Tf 0 Tr 50 {y_pos} Td ({text}) Tj ET".encode("ascii")
            )

        # Footer page number
        lines.append(f"BT /F1 9 Tf 0 Tr 200 40 Td (- {p_idx} -) Tj ET".encode("ascii"))

        cs = DecodedStreamObject()
        cs.set_data(b"\n".join(lines))
        page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_novel_with_chapter_ornament_pdf(path: Path) -> Path:
    """Generate a novel page containing text AND a small chapter divider ornament.

    Image is 200x50 px (< min_width 500px).
    Must NOT be extracted alone; must trigger RENDER to preserve the novel layout.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=420, height=595)
    font_ref = _add_standard_font(writer)

    # 200x50 px decorative ornament (small image)
    ornament_bytes = _make_jpeg_bytes(200, 50, (60, 60, 60))
    img_obj = DecodedStreamObject()
    img_obj.set_data(ornament_bytes)
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(200)
    img_obj[NameObject("/Height")] = NumberObject(50)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    img_ref = writer._add_object(img_obj)

    res = DictionaryObject()
    xobjs = DictionaryObject()
    xobjs[NameObject("/Im0")] = img_ref
    res[NameObject("/XObject")] = xobjs
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    res[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = res

    # Content: Chapter title + decorative ornament image + novel paragraph text
    cs = DecodedStreamObject()
    content_lines = [
        b"BT /F1 16 Tf 0 Tr 140 520 Td (Chapter IV: The Morlocks) Tj ET",
        # Draw ornament centered at y=470, width=100 pt, height=25 pt
        b"q 100 0 0 25 160 475 cm /Im0 Do Q",
        b"BT /F1 10 Tf 0 Tr 50 430 Td (It is very difficult to describe the sights that met my eyes as I descended.) Tj ET",
        b"BT /F1 10 Tf 0 Tr 50 405 Td (The darkness seemed impenetrable, yet cold hands reached from the shadows.) Tj ET",
        b"BT /F1 10 Tf 0 Tr 50 380 Td (I struck a match, and in its momentary flare, I caught sight of them.) Tj ET",
    ]
    cs.set_data(b"\n".join(content_lines))
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_light_novel_complete_volume_pdf(path: Path) -> Path:
    """Generate a realistic 10-page light novel complete volume.

    Page 1: Full-color Cover Illustration (1200x1600 px) -> EXTRACT
    Page 2: Full-color Pinup Insert (1200x1600 px) -> EXTRACT
    Page 3: Table of Contents (Pure text) -> RENDER
    Page 4: Chapter 1 with Header Ornament (200x50 px icon) -> RENDER
    Page 5: Chapter 1 Prose Body (Pure text) -> RENDER
    Page 6: Chapter 1 Prose Body (Pure text) -> RENDER
    Page 7: Blank Page between chapters -> BLANK
    Page 8: Chapter 2 Prose Body (Pure text) -> RENDER
    Page 9: Colophon / Afterword (Pure text) -> RENDER
    Page 10: Blank End Page -> BLANK
    """
    writer = PdfWriter()
    font_ref = _add_standard_font(writer)

    # --- Page 1: Cover Illustration ---
    p1 = writer.add_blank_page(width=600, height=800)
    cov_bytes = _make_jpeg_bytes(1200, 1600, (220, 60, 60))
    img1 = DecodedStreamObject()
    img1.set_data(cov_bytes)
    img1[NameObject("/Type")] = NameObject("/XObject")
    img1[NameObject("/Subtype")] = NameObject("/Image")
    img1[NameObject("/Width")] = NumberObject(1200)
    img1[NameObject("/Height")] = NumberObject(1600)
    img1[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img1[NameObject("/BitsPerComponent")] = NumberObject(8)
    img1[NameObject("/Filter")] = NameObject("/DCTDecode")
    ref1 = writer._add_object(img1)
    r1 = DictionaryObject()
    x1 = DictionaryObject()
    x1[NameObject("/Im0")] = ref1
    r1[NameObject("/XObject")] = x1
    p1[NameObject("/Resources")] = r1
    c1 = DecodedStreamObject()
    c1.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    p1[NameObject("/Contents")] = writer._add_object(c1)

    # --- Page 2: Pinup Insert ---
    p2 = writer.add_blank_page(width=600, height=800)
    pin_bytes = _make_jpeg_bytes(1200, 1600, (60, 120, 220))
    img2 = DecodedStreamObject()
    img2.set_data(pin_bytes)
    img2[NameObject("/Type")] = NameObject("/XObject")
    img2[NameObject("/Subtype")] = NameObject("/Image")
    img2[NameObject("/Width")] = NumberObject(1200)
    img2[NameObject("/Height")] = NumberObject(1600)
    img2[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img2[NameObject("/BitsPerComponent")] = NumberObject(8)
    img2[NameObject("/Filter")] = NameObject("/DCTDecode")
    ref2 = writer._add_object(img2)
    r2 = DictionaryObject()
    x2 = DictionaryObject()
    x2[NameObject("/Im0")] = ref2
    r2[NameObject("/XObject")] = x2
    p2[NameObject("/Resources")] = r2
    c2 = DecodedStreamObject()
    c2.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    p2[NameObject("/Contents")] = writer._add_object(c2)

    # Helper for text pages
    def _add_text_page(title: str, text_lines: list[str]) -> None:
        p = writer.add_blank_page(width=600, height=800)
        res = DictionaryObject()
        f = DictionaryObject()
        f[NameObject("/F1")] = font_ref
        res[NameObject("/Font")] = f
        p[NameObject("/Resources")] = res
        stream_cmds = [f"BT /F1 16 Tf 0 Tr 50 720 Td ({title}) Tj ET".encode("ascii")]
        for i, t in enumerate(text_lines):
            stream_cmds.append(
                f"BT /F1 11 Tf 0 Tr 50 {670 - i * 26} Td ({t}) Tj ET".encode("ascii")
            )
        cs_obj = DecodedStreamObject()
        cs_obj.set_data(b"\n".join(stream_cmds))
        p[NameObject("/Contents")] = writer._add_object(cs_obj)

    # --- Page 3: Table of Contents ---
    _add_text_page(
        "TABLE OF CONTENTS",
        [
            "Prologue: The Portal Opens ............ Page 4",
            "Chapter 1: Encounter in the Forest ..... Page 5",
            "Chapter 2: The Ancient Citadel ........ Page 8",
            "Epilogue & Author's Note .............. Page 9",
        ],
    )

    # --- Page 4: Chapter 1 with header ornament (< 500px) ---
    p4 = writer.add_blank_page(width=600, height=800)
    orn_bytes = _make_jpeg_bytes(180, 40, (50, 50, 50))
    img4 = DecodedStreamObject()
    img4.set_data(orn_bytes)
    img4[NameObject("/Type")] = NameObject("/XObject")
    img4[NameObject("/Subtype")] = NameObject("/Image")
    img4[NameObject("/Width")] = NumberObject(180)
    img4[NameObject("/Height")] = NumberObject(40)
    img4[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img4[NameObject("/BitsPerComponent")] = NumberObject(8)
    img4[NameObject("/Filter")] = NameObject("/DCTDecode")
    ref4 = writer._add_object(img4)
    r4 = DictionaryObject()
    x4 = DictionaryObject()
    x4[NameObject("/Im0")] = ref4
    r4[NameObject("/XObject")] = x4
    f4 = DictionaryObject()
    f4[NameObject("/F1")] = font_ref
    r4[NameObject("/Font")] = f4
    p4[NameObject("/Resources")] = r4
    c4 = DecodedStreamObject()
    c4.set_data(
        b"BT /F1 18 Tf 0 Tr 50 720 Td (Prologue: The Portal Opens) Tj ET\n"
        b"q 90 0 0 20 250 680 cm /Im0 Do Q\n"
        b"BT /F1 11 Tf 0 Tr 50 630 Td (The light flared suddenly, casting sharp shadows across the stone floor.) Tj ET\n"
        b"BT /F1 11 Tf 0 Tr 50 600 Td (Nobody had expected the barrier to break so soon.) Tj ET"
    )
    p4[NameObject("/Contents")] = writer._add_object(c4)

    # --- Page 5: Chapter 1 Body ---
    _add_text_page(
        "Chapter 1: Encounter in the Forest",
        [
            "The ancient trees reached high into the grey autumn sky.",
            "Leaves rustled underfoot as the scout made her way along the winding trail.",
            "In the distance, the faint sound of running water promised a place to rest.",
            "She checked her equipment, tightened the straps of her pack, and pushed onward.",
        ],
    )

    # --- Page 6: Chapter 1 Body (Continued) ---
    _add_text_page(
        "Chapter 1 (Continued)",
        [
            "By nightfall, the forest had grown completely silent.",
            "A gentle mist rose from the valley floor, obscuring the path behind.",
            "Ahead, the silhouette of the ruined tower stood stark against the stars.",
            "This was the destination she had sought for three long months.",
        ],
    )

    # --- Page 7: Blank Intermission Page ---
    writer.add_blank_page(width=600, height=800)

    # --- Page 8: Chapter 2 Body ---
    _add_text_page(
        "Chapter 2: The Ancient Citadel",
        [
            "Morning brought cold rain and biting wind.",
            "The gates of the citadel hung ajar, rusted hinges groaning in the gale.",
            "Inside the courtyard, ancient statues stood silent vigil over forgotten halls.",
            "Every step echoed through the immense stone corridors.",
        ],
    )

    # --- Page 9: Afterword ---
    _add_text_page(
        "Author's Afterword",
        [
            "Thank you for reading Volume 1 of this journey.",
            "I would like to thank my editor and the illustrator for their wonderful work.",
            "Volume 2 will continue the journey across the northern mountains.",
            "See you in the next volume!",
        ],
    )

    # --- Page 10: Blank End Page ---
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


