"""Text layer analysis for PDF pages and Form XObjects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

TEXT_SHOW_OPS: set[bytes] = {b"Tj", b"TJ", b"'", b'"'}


def _inspect_form_xobject(
    target: object,
    parent_res: object,
    depth: int,
    inspect_fn: Callable[[object, object, int], tuple[bool, bool]],
) -> tuple[bool, bool]:
    """Inspect nested Form XObject ContentStream for text operators."""
    if not isinstance(target, Mapping) or target.get("/Subtype") != "/Form":
        return False, False

    try:
        form_res = target.get("/Resources", parent_res)
        if hasattr(form_res, "get_object"):
            form_res = form_res.get_object()
        return inspect_fn(target, form_res, depth + 1)
    except Exception:
        return False, False


def _inspect_stream_ops(
    cs: Any,
    res_dict: object,
    depth: int,
    inspect_fn: Callable[[object, object, int], tuple[bool, bool]],
) -> tuple[bool, bool]:
    """Iterate ContentStream operations detecting text rendering and Form XObjects."""
    current_tr = 0
    has_vis = False
    has_invis = False

    for args, op in cs.operations:
        if op == b"Tr" and args:
            try:
                current_tr = int(args[0])
            except Exception:
                current_tr = 0
        elif op in TEXT_SHOW_OPS:
            if current_tr == 3:
                has_invis = True
            else:
                has_vis = True
        elif op == b"Do" and args and isinstance(res_dict, Mapping):
            try:
                xobjs = res_dict.get("/XObject", {})
                if hasattr(xobjs, "get_object"):
                    xobjs = xobjs.get_object()
                if isinstance(xobjs, Mapping):
                    target = xobjs.get(args[0])
                    if hasattr(target, "get_object"):
                        target = target.get_object()
                    sub_vis, sub_invis = _inspect_form_xobject(
                        target, res_dict, depth, inspect_fn
                    )
                    has_vis = has_vis or sub_vis
                    has_invis = has_invis or sub_invis
            except Exception:
                pass

    return has_vis, has_invis


def _inspect_stream(
    stream_obj: object,
    res_dict: object,
    reader: object = None,
    depth: int = 0,
) -> tuple[bool, bool]:
    """Inspect stream using pypdf ContentStream with recursion limit."""
    if depth > 3 or stream_obj is None:
        return False, False

    try:
        from pypdf.generic import ContentStream

        cs = ContentStream(stream_obj, reader)

        def _recurse(s: object, r: object, d: int) -> tuple[bool, bool]:
            return _inspect_stream(s, r, reader, d)

        return _inspect_stream_ops(cs, res_dict, depth, _recurse)
    except Exception:
        return False, False


def analyze_page_text_layers(page: object, reader: object = None) -> tuple[bool, bool]:
    """Inspect page ContentStream operations for visible and invisible (OCR) text.

    Supports top-level ContentStreams as well as nested Form XObjects invoked by 'Do'.
    Falls back to page.extract_text() if streams contain no text operators.

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

    resources = None
    if hasattr(page, "get"):
        try:
            resources = page.get("/Resources")
            if hasattr(resources, "get_object"):
                resources = resources.get_object()
        except Exception:
            resources = None

    has_visible = False
    has_invisible = False
    if contents is not None:
        has_visible, has_invisible = _inspect_stream(contents, resources, reader)

    if not has_visible and not has_invisible and hasattr(page, "extract_text"):
        try:
            extracted = page.extract_text()
            if isinstance(extracted, str) and bool(extracted.strip()):
                return True, False
        except Exception:
            pass

    return has_visible, has_invisible
