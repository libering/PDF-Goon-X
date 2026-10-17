"""Property-based tests for analyze module invariants (Hypothesis).

Feature: fix-detection-algorithm
Covers Property 4: 1-bit Mask Preservation Invariant (Req 3.3-3.5).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.analyze import (
    decide_processing_mode,
    is_true_pdf_mask,
)
from pdf_goon.models import (
    ImageInfo,
    PageInfo,
    ProcessingMode,
)

# Keys that define a true PDF mask per ISO 32000-1
MASK_KEYS = {"/ImageMask", "/SMask", "/Mask"}

# Safe printable text for arbitrary PDF dictionary keys/values
safe_strings = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Zs")),
    min_size=1,
    max_size=30,
)

non_mask_keys = safe_strings.filter(lambda k: k not in MASK_KEYS)


@settings(max_examples=100)
@given(
    d=st.dictionaries(
        keys=non_mask_keys,
        values=st.one_of(
            st.integers(),
            st.booleans(),
            st.text(),
            st.dictionaries(keys=st.text(), values=st.text()),
        ),
        max_size=15,
    ),
    bpc=st.integers(min_value=1, max_value=16),
)
def test_prop4_non_mask_dict_is_never_mask(d: dict, bpc: int) -> None:
    """Property 4a: Any XObject dictionary lacking /ImageMask, /SMask, /Mask is never a mask."""
    xobj = dict(d)
    xobj["/BitsPerComponent"] = bpc
    xobj["/Width"] = 1000
    xobj["/Height"] = 1000
    # Must evaluate to False regardless of 1-bit depth
    assert is_true_pdf_mask(xobj) is False


@settings(max_examples=50)
@given(
    mask_val=st.booleans(),
    d=st.dictionaries(keys=non_mask_keys, values=st.integers(), max_size=5),
)
def test_prop4_mask_dict_is_stencil_mask(mask_val: bool, d: dict) -> None:
    """Property 4b: Only an XObject dictionary with /ImageMask True is recognized as a mask."""
    xobj = dict(d)
    xobj["/ImageMask"] = mask_val
    assert is_true_pdf_mask(xobj) is (mask_val is True)


@settings(max_examples=50)
@given(
    mask_key=st.sampled_from(["/SMask", "/Mask"]),
    d=st.dictionaries(keys=non_mask_keys, values=st.integers(), max_size=5),
)
def test_prop4_attached_mask_is_not_stencil_mask(mask_key: str, d: dict) -> None:
    """Property 4c: Parent images with attached /SMask or /Mask are not treated as stencil masks."""
    xobj = dict(d)
    xobj[mask_key] = {}
    assert is_true_pdf_mask(xobj) is False


@settings(max_examples=100)
@given(
    img_w=st.integers(min_value=500, max_value=8000),
    img_h=st.integers(min_value=500, max_value=8000),
    page_w=st.floats(min_value=200.0, max_value=2000.0),
    page_h=st.floats(min_value=200.0, max_value=2000.0),
)
def test_prop4_1bit_page_never_decides_blank(
    img_w: int, img_h: int, page_w: float, page_h: float
) -> None:
    """Property 4d: A page with a single 1-bit content image and no text is never BLANK."""
    images = [
        ImageInfo(
            width=img_w,
            height=img_h,
            color="1",
            is_mask=False,
        )
    ]
    page_info = PageInfo(width_pts=page_w, height_pts=page_h)
    decision = decide_processing_mode(
        images=images,
        page_info=page_info,
        min_width=100,
        dpi_text=300,
        force_render=False,
    )
    # Never classified as BLANK
    assert decision.mode in (ProcessingMode.EXTRACT, ProcessingMode.RENDER)
    assert decision.mode != ProcessingMode.BLANK


def test_prop4_mask_only_page_renders_never_blank() -> None:
    """Property 4e: A page with only mask images and no text renders instead of dropping as BLANK."""
    images = [
        ImageInfo(
            width=1000,
            height=1000,
            color="1",
            is_mask=True,
        )
    ]
    page_info = PageInfo(width_pts=595.0, height_pts=842.0)
    decision = decide_processing_mode(
        images=images,
        page_info=page_info,
        min_width=100,
        dpi_text=300,
        force_render=False,
    )
    assert decision.mode == ProcessingMode.RENDER
    assert "mask images" in decision.reason
