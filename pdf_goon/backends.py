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
class ExtractBackend(Protocol):
    """Protocol for image extraction from PDF pages."""

    def extract_images(
        self,
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
    ) -> list[Path]: ...


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


# --- Default implementations ---


class PypdfAnalyzeBackend:
    """Default analysis backend wrapping analyze.py functions."""

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


class Pypdfium2RenderBackend:
    """Default render backend wrapping extract.py render_page."""

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
