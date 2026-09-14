"""Property-based tests for Backend Protocol exception propagation.

Feature: codebase-improvements
Covers Property 9: Backend exception propagation.

These tests are engine-agnostic: they do NOT require pypdf / pypdfium2 to be
installed. Failures are injected at the module's designed seams (the lazy
engine-import site for extract, the `run` callable injection point for render)
so the propagation contract can be verified in any environment.
"""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import pdf_goon.extract as extract_mod
from pdf_goon.backends import (
    PypdfAnalyzeBackend,
    PypdfExtractBackend,
    Pypdfium2RenderBackend,
)
from pdf_goon.models import (
    PageInfo,
    PdfGoonError,
    SubprocessError,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Non-empty, printable exception messages (avoid control chars that Hypothesis
# might otherwise inject, keeping counterexamples human-readable).
_messages = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Zs")),
    min_size=1,
    max_size=60,
)

# Positive 1-indexed page numbers within a realistic bound.
_page_nums = st.integers(min_value=1, max_value=500)

# The full set of underlying exception types a real engine layer could raise.
# Using distinct constructors keeps generation lazy so Hypothesis can shrink
# on the *message* dimension independently of the exception type.
_exc_factories = st.sampled_from(
    [
        lambda msg: ValueError(msg),
        lambda msg: RuntimeError(msg),
        lambda msg: KeyError(msg),
        lambda msg: OSError(msg),
        lambda msg: IndexError(msg),
        lambda msg: TypeError(msg),
    ]
)


def _install_fake_pypdf(raiser: Exception) -> types.ModuleType:
    """Build a fake `pypdf` module whose PdfReader raises `raiser`.

    Why: the real pypdf may be absent in CI/dev environments. Injecting a fake
    module via sys.modules lets `import pypdf` inside extract_images succeed and
    then fail deterministically with a KNOWN cause object, so we can assert
    __cause__ identity regardless of whether pypdf is installed.
    """
    fake = types.ModuleType("pypdf")

    def _reader(*_args: object, **_kwargs: object) -> object:
        raise raiser

    fake.PdfReader = _reader  # type: ignore[attr-defined]
    return fake


# ---------------------------------------------------------------------------
# Feature: codebase-improvements, Property 9: Backend exception propagation
#
# For any exception raised by a backend implementation (Analyze / Extract /
# Render) the system propagates it through the PdfGoonError hierarchy,
# preserving the original exception as __cause__.
#
# The default backends are the concrete Protocol implementations and encode
# the "current implementation" contract that Requirement 5.4 anchors on:
# engine-layer failures are wrapped as PdfGoonError with `from exc`.
# ---------------------------------------------------------------------------


class TestDefaultBackendExceptionPropagation:
    """Default backends propagate engine failures through PdfGoonError.

    **Validates: Requirements 5.4**
    """

    @settings(max_examples=100)
    @given(msg=_messages, page_num=_page_nums, make_exc=_exc_factories)
    def test_extract_backend_wraps_engine_error_as_pdfgoonerror(
        self, msg: str, page_num: int, make_exc: object
    ) -> None:
        """Any engine exception surfaces as PdfGoonError with __cause__ set.

        PypdfExtractBackend delegates to extract.extract_images, whose engine
        layer may raise arbitrary exceptions. The backend must re-raise them
        through the PdfGoonError hierarchy, preserving the original as
        __cause__ (fail-fast, no swallowing).
        """
        original = make_exc(msg)  # type: ignore[operator]
        backend = PypdfExtractBackend()

        # extract_images opens the PDF on disk BEFORE calling PdfReader, so the
        # file must exist for the fake engine to become the failure point.
        with tempfile.TemporaryDirectory(prefix="pbt_extract_") as tmp:
            pdf_path = Path(tmp) / "input.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 dummy")

            # Inject a fake pypdf so the lazy `import pypdf` succeeds and then
            # the engine call raises our known exception object.
            fake_pypdf = _install_fake_pypdf(original)
            with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
                with pytest.raises(PdfGoonError) as exc_info:
                    backend.extract_images(
                        pdf_path,
                        page_num,
                        Path(tmp) / "out_prefix",
                    )

        # Propagated through the hierarchy...
        assert isinstance(exc_info.value, PdfGoonError)
        # ...and the original engine exception is preserved as the cause.
        assert exc_info.value.__cause__ is original

    @settings(max_examples=100)
    @given(msg=_messages, page_num=_page_nums)
    def test_render_wraps_subprocess_error_preserving_cause(
        self, msg: str, page_num: int
    ) -> None:
        """A SubprocessError from the worker surfaces as PdfGoonError w/ cause.

        The render backend delegates to extract.render_page, whose designed
        seam is the injectable `run` callable. When `run` raises SubprocessError
        (the only failure mode render_page wraps), the function must re-raise a
        PdfGoonError preserving the SubprocessError as __cause__.
        """
        sub_err = SubprocessError(tool="worker", exit_code=1, stderr=msg)

        def failing_run(cmd: list[str]) -> str:
            raise sub_err

        # Exercise the wrapping contract via the designed injection point.
        with pytest.raises(PdfGoonError) as exc_info:
            extract_mod.render_page(
                Path("/nonexistent/input.pdf"),
                page_num,
                Path("/tmp/render_prefix"),
                150.0,
                PageInfo(width_pts=612.0, height_pts=792.0),
                run=failing_run,
            )

        assert isinstance(exc_info.value, PdfGoonError)
        assert exc_info.value.__cause__ is sub_err

    def test_render_backend_delegates_to_extract_render_page(self) -> None:
        """Pypdfium2RenderBackend forwards to extract.render_page verbatim.

        Confirms the backend adapter is a transparent delegate, so the
        wrapping contract verified above is the one the backend relies on.
        """
        sentinel: list[Path] = [Path("/tmp/out.png")]
        captured: dict[str, object] = {}

        def fake_render(
            pdf_path: Path,
            page_num: int,
            output_prefix: Path,
            dpi: float,
            page_info: PageInfo,
        ) -> list[Path]:
            captured["pdf_path"] = pdf_path
            captured["page_num"] = page_num
            return sentinel

        backend = Pypdfium2RenderBackend()
        with patch("pdf_goon.extract.render_page", side_effect=fake_render):
            result = backend.render_page(
                Path("/in.pdf"),
                3,
                Path("/tmp/prefix"),
                200.0,
                PageInfo(width_pts=612.0, height_pts=792.0),
            )

        assert result is sentinel
        assert captured["page_num"] == 3

    @settings(max_examples=100)
    @given(msg=_messages, page_num=_page_nums, make_exc=_exc_factories)
    def test_analyze_backend_get_image_data_propagates(
        self, msg: str, page_num: int, make_exc: object
    ) -> None:
        """Engine failure in analyze.get_image_data propagates unchanged.

        AnalyzeBackend has no wrapping contract of its own — analyze functions
        raise directly. The property that must hold is fail-fast propagation:
        the exception is NOT swallowed by the backend adapter, so the very same
        object reaches the caller.
        """
        original = make_exc(msg)  # type: ignore[operator]
        backend = PypdfAnalyzeBackend()

        with patch("pdf_goon.analyze.get_image_data", side_effect=original):
            with pytest.raises(type(original)) as exc_info:
                backend.get_image_data(Path("/nonexistent/input.pdf"), page_num)

        # Same object — the adapter is a transparent pass-through (no swallow).
        assert exc_info.value is original
