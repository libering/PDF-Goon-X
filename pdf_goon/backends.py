"""Backend Protocol definitions for engine abstraction."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pdf_goon.models import ImageInfo, PageInfo


@runtime_checkable
class AnalyzeBackend(Protocol):
    """Protocol for PDF analysis operations."""

    def get_page_count(self, pdf_path: Path) -> int | None: ...

    def get_image_data(
        self,
        pdf_path: Path,
        page_num: int,
    ) -> tuple[list[ImageInfo], list[str], bool]: ...

    def get_page_info(self, pdf_path: Path, page_num: int) -> PageInfo: ...


@runtime_checkable
class PdfAnalyzeSession(Protocol):
    """Protocol for an active PDF analysis session."""

    def inspect_page(
        self, page_num: int
    ) -> tuple[list[ImageInfo], list[str], bool, PageInfo]: ...

    def close(self) -> None: ...


@runtime_checkable
class SessionAnalyzeBackend(AnalyzeBackend, Protocol):
    """Protocol for analysis backends supporting sequential session inspection."""

    def open_session(self, pdf_path: Path) -> PdfAnalyzeSession: ...


@runtime_checkable
class ExtractBackend(Protocol):
    """Protocol for image extraction from PDF pages."""

    def extract_images(
        self,
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
    ) -> list[Path]: ...


@runtime_checkable
class PdfExtractSession(Protocol):
    """Protocol for an active PDF extraction session."""

    def extract_images(
        self,
        page_num: int,
        output_prefix: Path,
    ) -> list[Path]: ...

    def close(self) -> None: ...


@runtime_checkable
class SessionExtractBackend(ExtractBackend, Protocol):
    """Protocol for extraction backends supporting sequential session extraction."""

    def open_session(self, pdf_path: Path) -> PdfExtractSession: ...


@runtime_checkable
class RenderBackend(Protocol):
    """Protocol for PDF page rendering."""

    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
        dpi: float,
        page_info: PageInfo,
    ) -> list[Path]: ...


@runtime_checkable
class BatchRenderBackend(RenderBackend, Protocol):
    """Protocol for batch PDF page rendering."""

    def render_batch(
        self,
        pdf_path: Path,
        tasks: list[dict],
    ) -> list[Path]: ...


# --- Default implementations ---


class PypdfAnalyzeBackend:
    """Default analysis backend wrapping analyze.py functions and session."""

    def get_page_count(self, pdf_path: Path) -> int | None:
        from pdf_goon.analyze import get_page_count

        return get_page_count(pdf_path)

    def get_image_data(
        self,
        pdf_path: Path,
        page_num: int,
    ) -> tuple[list[ImageInfo], list[str], bool]:
        from pdf_goon.analyze import get_image_data

        return get_image_data(pdf_path, page_num)

    def get_page_info(self, pdf_path: Path, page_num: int) -> PageInfo:
        from pdf_goon.analyze import get_page_info

        return get_page_info(pdf_path, page_num)

    def open_session(self, pdf_path: Path) -> PdfAnalyzeSession:
        from pdf_goon.analyze import PypdfSession

        return PypdfSession(pdf_path)


class PypdfExtractBackend:
    """Default extraction backend wrapping extract.py."""

    def extract_images(
        self,
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
    ) -> list[Path]:
        from pdf_goon.extract import extract_images

        return extract_images(pdf_path, page_num, output_prefix)

    def open_session(self, pdf_path: Path) -> PdfExtractSession:
        from pdf_goon.extract import PypdfExtractSession

        return PypdfExtractSession(pdf_path)


class Pypdfium2RenderBackend:
    """Default render backend wrapping extract.py render_page and render_batch."""

    def render_page(
        self,
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
        dpi: float,
        page_info: PageInfo,
    ) -> list[Path]:
        from pdf_goon.extract import render_page

        return render_page(pdf_path, page_num, output_prefix, dpi, page_info)

    def render_batch(
        self,
        pdf_path: Path,
        tasks: list[dict],
    ) -> list[Path]:
        from pdf_goon.extract import render_batch

        return render_batch(pdf_path, tasks)
