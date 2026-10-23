# tests.test_analyze — Tests for pdf_goon.analyze page and image extraction

from pathlib import Path
from unittest.mock import MagicMock, patch

from pdf_goon.analyze import (
    analyze_page_text_layers,
    decide_processing_mode,
    get_image_data,
    get_page_count,
    get_page_info,
    is_true_pdf_mask,
    PypdfSession,
)
from pdf_goon.models import (
    PageInfo,
    ProcessingMode,
)


# --- Unit tests for get_page_count ---


DUMMY_PDF = Path("/tmp/test.pdf")
_mock_file = MagicMock()  # Reusable mock file object for open()


def test_get_page_count_returns_correct_count() -> None:
    """get_page_count extracts page count using pypdf."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_reader.return_value.pages = [1, 2, 3, 4, 5]
        result = get_page_count(DUMMY_PDF)
        assert result == 5


def test_get_page_count_returns_none_on_error() -> None:
    """get_page_count returns None when pypdf raises Exception."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader", side_effect=Exception("bad pdf")),
    ):
        result = get_page_count(DUMMY_PDF)
        assert result is None


# --- Unit tests for get_image_data ---


def test_get_image_data_parses_normal_images() -> None:
    """get_image_data correctly parses image entries using pypdf."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_img = MagicMock()
        mock_img.image.width = 1200
        mock_img.image.height = 800
        mock_img.image.mode = "RGB"

        mock_page = MagicMock()
        mock_page.images = [mock_img]
        mock_page.get.return_value = {}
        mock_reader.return_value.pages = [mock_page]

        images, masks, has_text = get_image_data(DUMMY_PDF, 1)

        assert len(images) == 1
        assert images[0].width == 1200
        assert images[0].height == 800
        assert images[0].color == "rgb"
        assert images[0].is_mask is False
        assert has_text is False


def test_is_true_pdf_mask() -> None:
    assert is_true_pdf_mask({"/ImageMask": True}) is True
    # Attached soft masks (/SMask) or chroma key masks (/Mask) do not make the parent image a mask
    assert is_true_pdf_mask({"/SMask": {}}) is False
    assert is_true_pdf_mask({"/Mask": [0, 0]}) is False
    # 1-bit image without mask keys is NOT a mask
    assert is_true_pdf_mask({"/BitsPerComponent": 1, "/Width": 1000}) is False
    assert is_true_pdf_mask({}) is False
    assert is_true_pdf_mask(None) is False
    assert is_true_pdf_mask("not a dict") is False


def test_analyze_page_text_layers_invisible_ocr_vs_visible() -> None:
    """analyze_page_text_layers distinguishes visible text from 3 Tr OCR text."""
    with patch("pypdf.generic.ContentStream") as mock_cs:
        # Case 1: Visible text (Tr default 0)
        mock_cs.return_value.operations = [
            ([], b"BT"),
            ([b"Visible text"], b"Tj"),
            ([], b"ET"),
        ]
        mock_page = MagicMock()
        mock_page.get_contents.return_value = MagicMock()
        has_vis, has_invis = analyze_page_text_layers(mock_page, None)
        assert has_vis is True
        assert has_invis is False

        # Case 2: Invisible OCR text (3 Tr)
        mock_cs.return_value.operations = [
            ([], b"BT"),
            ([3], b"Tr"),
            ([b"Invisible OCR text"], b"Tj"),
            ([], b"ET"),
        ]
        has_vis, has_invis = analyze_page_text_layers(mock_page, None)
        assert has_vis is False
        assert has_invis is True

        # Case 3: Empty operations / Font resource only (zero text operators)
        mock_cs.return_value.operations = [
            ([], b"q"),
            ([], b"Q"),
        ]
        has_vis, has_invis = analyze_page_text_layers(mock_page, None)
        assert has_vis is False
        assert has_invis is False


def test_get_image_data_identifies_mask() -> None:
    """get_image_data identifies masks using standard PDF mask dictionary keys."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_img1 = MagicMock()
        mock_img1.image.width = 800
        mock_img1.image.height = 600
        mock_img1.image.mode = "RGB"
        mock_img1.indirect_reference.get_object.return_value = {}

        mock_img2 = MagicMock()
        mock_img2.image.width = 800
        mock_img2.image.height = 600
        mock_img2.image.mode = "1"
        mock_img2.indirect_reference.get_object.return_value = {"/ImageMask": True}

        mock_page = MagicMock()
        mock_page.images = [mock_img1, mock_img2]
        mock_page.get_contents.return_value = None
        mock_page.extract_text.return_value = ""
        mock_reader.return_value.pages = [mock_page]

        images, masks, has_text = get_image_data(DUMMY_PDF, 1)

        assert len(masks) == 1
        assert masks[0] == "001"
        assert len(images) == 1
        assert images[0].color == "rgb"


def test_get_image_data_preserves_1bit_monochrome_novel() -> None:
    """1-bit monochrome scanned novel/line-art image without mask keys is preserved."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_img = MagicMock()
        mock_img.image.width = 1600
        mock_img.image.height = 2400
        mock_img.image.mode = "1"
        mock_img.indirect_reference.get_object.return_value = {
            "/Type": "/XObject",
            "/Subtype": "/Image",
            "/BitsPerComponent": 1,
        }

        mock_page = MagicMock()
        mock_page.images = [mock_img]
        mock_page.get_contents.return_value = None
        mock_page.extract_text.return_value = ""
        mock_reader.return_value.pages = [mock_page]

        images, masks, has_text = get_image_data(DUMMY_PDF, 1)

        assert len(masks) == 0
        assert len(images) == 1
        assert images[0].color == "1"
        assert images[0].is_mask is False
        assert has_text is False


def test_get_image_data_detects_text() -> None:
    """get_image_data detects visible text via content stream inspection."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
        patch("pypdf.generic.ContentStream") as mock_cs,
    ):
        mock_cs.return_value.operations = [
            ([], b"BT"),
            ([0], b"Tr"),
            ([b"Substantive visible text"], b"Tj"),
            ([], b"ET"),
        ]
        mock_page = MagicMock()
        mock_page.images = []
        mock_page.get_contents.return_value = MagicMock()
        mock_reader.return_value.pages = [mock_page]

        _, _, has_text = get_image_data(DUMMY_PDF, 1)
        assert has_text is True


def test_get_image_data_ignores_ocr_3tr_for_has_text() -> None:
    """get_image_data treats pages with only 3 Tr OCR text as has_text=False."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
        patch("pypdf.generic.ContentStream") as mock_cs,
    ):
        mock_cs.return_value.operations = [
            ([], b"BT"),
            ([3], b"Tr"),
            ([b"Invisible OCR text layer"], b"Tj"),
            ([], b"ET"),
        ]
        mock_page = MagicMock()
        mock_page.images = []
        mock_page.get_contents.return_value = MagicMock()
        mock_reader.return_value.pages = [mock_page]

        _, _, has_text = get_image_data(DUMMY_PDF, 1)
        assert has_text is False


def test_get_image_data_returns_empty_on_error() -> None:
    """get_image_data returns empty lists when pypdf fails."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader", side_effect=Exception("error")),
    ):
        images, masks, has_text = get_image_data(DUMMY_PDF, 1)

        assert images == []
        assert masks == []
        assert has_text is False


# --- Unit tests for get_page_info ---


def test_get_page_info_parses_dimensions() -> None:
    """get_page_info parses page dimensions using pypdf mediabox."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_page = MagicMock()
        mock_page.mediabox.width = 612.0
        mock_page.mediabox.height = 792.0
        mock_reader.return_value.pages = [mock_page]

        info = get_page_info(DUMMY_PDF, 1)

        assert abs(info.width_pts - 612.0) < 0.01
        assert abs(info.height_pts - 792.0) < 0.01


def test_get_page_info_returns_zero_on_failure() -> None:
    """get_page_info returns (0.0, 0.0) when pypdf fails."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader", side_effect=Exception("error")),
    ):
        info = get_page_info(DUMMY_PDF, 1)

        assert info.width_pts == 0.0
        assert info.height_pts == 0.0




def test_colortransform_0_routes_to_render() -> None:
    """Non-standard /ColorTransform 0 routes image to RENDER (D9, Req 9.2)."""
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
    ):
        mock_img = MagicMock()
        mock_img.image.width = 1600
        mock_img.image.height = 2400
        mock_img.image.mode = "RGB"
        mock_img.indirect_reference.get_object.return_value = {
            "/Type": "/XObject",
            "/Subtype": "/Image",
            "/DecodeParms": {"/ColorTransform": 0},
        }

        mock_page = MagicMock()
        mock_page.images = [mock_img]
        mock_page.get_contents.return_value = None
        mock_page.extract_text.return_value = ""
        mock_reader.return_value.pages = [mock_page]

        images, masks, has_text = get_image_data(DUMMY_PDF, 1)

        assert len(images) == 1
        assert images[0].color == "colortransform0"

        page_info = PageInfo(width_pts=600.0, height_pts=800.0)
        decision = decide_processing_mode(
            images,
            page_info,
            min_width=500,
            dpi_text=400,
            force_render=False,
            has_text=False,
        )

        assert decision.mode is ProcessingMode.RENDER
        assert "colortransform0" in decision.reason


def test_pypdf_session_inspect_page() -> None:
    """PypdfSession inspects page and associates geometry and text in a single pass (D7)."""
    import pypdfium2

    assert pypdfium2 is not None  # Pre-import so version.json read is not intercepted
    with (
        patch("builtins.open", return_value=_mock_file),
        patch("pypdf.PdfReader") as mock_reader,
        patch("pypdfium2.PdfDocument") as mock_doc,
    ):
        # Setup pypdf mocks
        mock_img = MagicMock()
        mock_img.image.width = 1200
        mock_img.image.height = 1800
        mock_img.image.mode = "RGB"
        mock_img.indirect_reference.get_object.return_value = {}

        mock_pypdf_page = MagicMock()
        mock_pypdf_page.images = [mock_img]
        mock_pypdf_page.get_contents.return_value = None
        mock_pypdf_page.extract_text.return_value = ""
        mock_reader.return_value.pages = [mock_pypdf_page]

        # Setup pypdfium2 page mocks
        mock_pdfium_page = MagicMock()
        mock_pdfium_page.get_size.return_value = (600.0, 900.0)
        mock_pdfium_page.get_rotation.return_value = 0
        mock_obj = MagicMock()
        mock_obj.get_bounds.return_value = (0.0, 0.0, 600.0, 900.0)
        mock_matrix = MagicMock()
        mock_matrix.a, mock_matrix.b, mock_matrix.c, mock_matrix.d = 1.0, 0.0, 0.0, 1.0
        mock_obj.get_matrix.return_value = mock_matrix
        mock_obj.get_quad_points.return_value = None
        mock_pdfium_page.get_objects.return_value = [mock_obj]
        mock_doc.return_value.__getitem__.return_value = mock_pdfium_page

        with PypdfSession(DUMMY_PDF) as session:
            images, masks, has_text, page_info = session.inspect_page(1)

            assert len(images) == 1
            assert images[0].width == 1200
            assert images[0].placed_bbox == (0.0, 0.0, 600.0, 900.0)
            assert images[0].has_rotation is False
            assert page_info.width_pts == 600.0
            assert page_info.height_pts == 900.0
            assert has_text is False
