"""Multi-page book and novel PDF generators for integration testing.

Covers:
- Realistic mixed book (cover, typography, 1-bit text, OCR layer, blank end)
- Pure text novel (running headers, chapters, footer pagination)
- Novel with chapter decorative ornament
- Light novel complete volume (color inserts, TOC, chapters, colophon)
"""

from __future__ import annotations

from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from tests.synthetic_fixtures import _make_1bit_compressed_bytes, _make_jpeg_bytes


def _add_standard_font(writer: PdfWriter) -> object:
    font_dict = DictionaryObject()
    font_dict[NameObject("/Type")] = NameObject("/Font")
    font_dict[NameObject("/Subtype")] = NameObject("/Type1")
    font_dict[NameObject("/BaseFont")] = NameObject("/Helvetica")
    return writer._add_object(font_dict)


def _add_mixed_p1_cover(writer: PdfWriter) -> None:
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
    p1[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): ref1})}
    )
    c1 = DecodedStreamObject()
    c1.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    p1[NameObject("/Contents")] = writer._add_object(c1)


def _add_mixed_p2_typography(writer: PdfWriter, font_ref: object) -> None:
    p2 = writer.add_blank_page(width=600, height=800)
    p2[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    c2 = DecodedStreamObject()
    c2.set_data(
        b"BT /F1 20 Tf 0 Tr 50 700 Td (PDF-Goon The Adventure) Tj /F1 12 Tf 0 Tr 50 650 Td (Copyright 2026) Tj ET"
    )
    p2[NameObject("/Contents")] = writer._add_object(c2)


def _add_mixed_p3_1bit(writer: PdfWriter) -> None:
    p3 = writer.add_blank_page(width=600, height=800)
    b3 = _make_1bit_compressed_bytes(1200, 1600)
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
    p3[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): ref3})}
    )
    c3 = DecodedStreamObject()
    c3.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    p3[NameObject("/Contents")] = writer._add_object(c3)


def _add_mixed_p4_ocr(writer: PdfWriter, font_ref: object) -> None:
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
    p4[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): ref4}),
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
        }
    )
    c4 = DecodedStreamObject()
    c4.set_data(
        b"q 600 0 0 800 0 0 cm /Im0 Do Q BT /F1 12 Tf 3 Tr 100 700 Td (Invisible OCR Text) Tj ET"
    )
    p4[NameObject("/Contents")] = writer._add_object(c4)


def make_multi_page_mixed_book_pdf(path: Path) -> Path:
    """Generate 5-page realistic mixed book."""
    writer = PdfWriter()
    font_ref = _add_standard_font(writer)

    _add_mixed_p1_cover(writer)
    _add_mixed_p2_typography(writer, font_ref)
    _add_mixed_p3_1bit(writer)
    _add_mixed_p4_ocr(writer, font_ref)
    writer.add_blank_page(width=600, height=800)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def _render_novel_page_content(
    p_idx: int, paragraphs: list[str], writer: PdfWriter, font_ref: object
) -> None:
    page = writer.add_blank_page(width=420, height=595)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    chap = ((p_idx - 1) // 3) + 1
    lines = [f"BT /F1 9 Tf 0 Tr 50 560 Td (CHAPTER {chap}) Tj ET".encode("ascii")]
    y_start = 480 if (p_idx == 1 or p_idx % 3 == 1) else 520
    if p_idx == 1 or p_idx % 3 == 1:
        lines.append(f"BT /F1 15 Tf 0 Tr 50 520 Td (Chapter {chap}) Tj ET".encode("ascii"))
    for idx, text in enumerate(paragraphs):
        y_pos = y_start - (idx * 24)
        if y_pos < 80:
            break
        lines.append(f"BT /F1 10 Tf 0 Tr 50 {y_pos} Td ({text}) Tj ET".encode("ascii"))
    lines.append(f"BT /F1 9 Tf 0 Tr 200 40 Td (- {p_idx} -) Tj ET".encode("ascii"))
    cs = DecodedStreamObject()
    cs.set_data(b"\n".join(lines))
    page[NameObject("/Contents")] = writer._add_object(cs)


def make_pure_text_novel_pdf(path: Path, num_pages: int = 10) -> Path:
    """Generate an authentic multi-page pure text novel (A5 format, 420x595 pt)."""
    writer = PdfWriter()
    font_ref = _add_standard_font(writer)
    sample_paragraphs = [
        "The Time Traveller was expounding a recondite matter to us.",
        "His grey eyes shone and twinkled, and his usually pale face was flushed.",
        "The fire burned brightly, and the soft radiance illuminated the room.",
        "It was at this moment that he began his singular demonstration.",
        "Drawing a small crystal mechanism from his pocket, he placed it carefully.",
    ]
    for p_idx in range(1, num_pages + 1):
        _render_novel_page_content(p_idx, sample_paragraphs, writer, font_ref)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def make_novel_with_chapter_ornament_pdf(path: Path) -> Path:
    """Generate a novel page containing text AND a small chapter divider ornament."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=420, height=595)
    font_ref = _add_standard_font(writer)

    img_obj = DecodedStreamObject()
    img_obj.set_data(_make_jpeg_bytes(200, 50, (60, 60, 60)))
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(200)
    img_obj[NameObject("/Height")] = NumberObject(50)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    ref = writer._add_object(img_obj)

    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): ref}),
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
        }
    )
    cs = DecodedStreamObject()
    cs.set_data(
        b"BT /F1 16 Tf 0 Tr 140 520 Td (Chapter IV) Tj ET\n"
        b"q 100 0 0 25 160 475 cm /Im0 Do Q\n"
        b"BT /F1 10 Tf 0 Tr 50 430 Td (Text line 1) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(cs)

    with open(path, "wb") as f:
        writer.write(f)
    return path


def _add_ln_full_image_page(
    writer: PdfWriter, color: tuple[int, int, int]
) -> None:
    p = writer.add_blank_page(width=600, height=800)
    img_obj = DecodedStreamObject()
    img_obj.set_data(_make_jpeg_bytes(1200, 1600, color))
    img_obj[NameObject("/Type")] = NameObject("/XObject")
    img_obj[NameObject("/Subtype")] = NameObject("/Image")
    img_obj[NameObject("/Width")] = NumberObject(1200)
    img_obj[NameObject("/Height")] = NumberObject(1600)
    img_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    img_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    img_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    ref = writer._add_object(img_obj)
    p[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): ref})}
    )
    cs = DecodedStreamObject()
    cs.set_data(b"q 600 0 0 800 0 0 cm /Im0 Do Q")
    p[NameObject("/Contents")] = writer._add_object(cs)


def _add_ln_text_page(
    writer: PdfWriter, font_ref: object, title: str, body: list[str]
) -> None:
    p = writer.add_blank_page(width=600, height=800)
    p[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    lines = [f"BT /F1 18 Tf 0 Tr 60 720 Td ({title}) Tj ET".encode("ascii")]
    for idx, text in enumerate(body):
        lines.append(
            f"BT /F1 11 Tf 0 Tr 60 {660 - idx * 28} Td ({text}) Tj ET".encode("ascii")
        )
    cs = DecodedStreamObject()
    cs.set_data(b"\n".join(lines))
    p[NameObject("/Contents")] = writer._add_object(cs)


def _add_ln_chapter1_ornament_page(
    writer: PdfWriter, font_ref: object
) -> None:
    p4 = writer.add_blank_page(width=600, height=800)
    orn_obj = DecodedStreamObject()
    orn_obj.set_data(_make_jpeg_bytes(200, 50, (40, 40, 40)))
    orn_obj[NameObject("/Type")] = NameObject("/XObject")
    orn_obj[NameObject("/Subtype")] = NameObject("/Image")
    orn_obj[NameObject("/Width")] = NumberObject(200)
    orn_obj[NameObject("/Height")] = NumberObject(50)
    orn_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    orn_obj[NameObject("/BitsPerComponent")] = NumberObject(8)
    orn_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    ref_orn = writer._add_object(orn_obj)
    p4[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): ref_orn}),
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref}),
        }
    )
    c4 = DecodedStreamObject()
    c4.set_data(
        b"BT /F1 20 Tf 0 Tr 60 720 Td (Chapter 1: Arrival) Tj ET\n"
        b"q 120 0 0 30 240 660 cm /Im0 Do Q\n"
        b"BT /F1 11 Tf 0 Tr 60 610 Td (The wind whistled across the desolate plains.) Tj ET"
    )
    p4[NameObject("/Contents")] = writer._add_object(c4)


def make_light_novel_complete_volume_pdf(path: Path) -> Path:
    """Generate a realistic 10-page light novel complete volume."""
    writer = PdfWriter()
    font_ref = _add_standard_font(writer)

    _add_ln_full_image_page(writer, (220, 60, 60))  # P1: Cover
    _add_ln_full_image_page(writer, (60, 120, 220))  # P2: Pinup
    _add_ln_text_page(writer, font_ref, "Table of Contents", ["Chapter 1", "Chapter 2"])  # P3
    _add_ln_chapter1_ornament_page(writer, font_ref)  # P4
    _add_ln_text_page(writer, font_ref, "Chapter 1 Continued", ["Body paragraph"])  # P5
    _add_ln_text_page(writer, font_ref, "Chapter 1 Ending", ["Body paragraph"])  # P6
    writer.add_blank_page(width=600, height=800)  # P7: Blank
    _add_ln_text_page(writer, font_ref, "Chapter 2", ["Body paragraph"])  # P8
    _add_ln_text_page(writer, font_ref, "Afterword", ["Author note"])  # P9
    writer.add_blank_page(width=600, height=800)  # P10: Blank

    with open(path, "wb") as f:
        writer.write(f)
    return path
