"""Image extraction and page rendering."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pdf_goon.models import PageInfo
from pdf_goon.tools import run_command


def _save_extracted_image(
    img_file: Any,
    img_idx: int,
    page_num: int,
    output_prefix: Path,
) -> Path:
    """Save a single embedded image file with format resolution and memory cleanup."""
    suffix = Path(img_file.name).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    if suffix not in (".png", ".jpg"):
        suffix = ".png"

    out_path = output_prefix.parent / f"{output_prefix.name}-{img_idx:03d}{suffix}"

    # pypdf's img_file.data for JPEGs is valid DCTDecode bytes.
    # For FlateDecode (PNG), save using PIL to guarantee valid PNG headers and close cleanly.
    if suffix == ".jpg":
        with open(out_path, "wb") as out_f:
            out_f.write(img_file.data)
    else:
        pil_image = img_file.image
        if pil_image is None:
            raise ValueError(
                f"PIL image unavailable for image {img_idx} on page {page_num}"
            )
        try:
            pil_image.save(out_path, format="PNG")
        finally:
            if hasattr(pil_image, "close"):
                try:
                    pil_image.close()
                except Exception:
                    pass

    return out_path


def _extract_page_images_from_page(
    page: Any,
    page_num: int,
    output_prefix: Path,
) -> list[Path]:
    """Extract embedded images from a resolved pypdf PageObject."""
    output_paths = []
    for img_idx, img_file in enumerate(page.images):
        out_path = _save_extracted_image(img_file, img_idx, page_num, output_prefix)
        output_paths.append(out_path)
    return sorted(output_paths)


def extract_images(
    pdf_path: Path,
    page_num: int,
    output_prefix: Path,
    *,
    reader: Any = None,
) -> list[Path]:
    """Extract embedded images from a single PDF page using pypdf."""
    from pdf_goon.models import PdfGoonError

    try:
        import pypdf

        if reader is not None:
            page = reader.pages[page_num - 1]
            return _extract_page_images_from_page(page, page_num, output_prefix)

        with open(pdf_path, "rb") as f:
            reader_obj = pypdf.PdfReader(f)
            page = reader_obj.pages[page_num - 1]
            return _extract_page_images_from_page(page, page_num, output_prefix)
    except Exception as exc:
        raise PdfGoonError(
            f"Failed to extract images from page {page_num} with pypdf: {exc}"
        ) from exc


class PypdfExtractSession:
    """Sequential extraction session holding an open reader handle."""

    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = pdf_path
        self._f: Any = open(pdf_path, "rb")
        self.reader: Any = None
        try:
            import pypdf

            self.reader = pypdf.PdfReader(self._f)
        except Exception:
            self.close()
            raise

    def extract_images(self, page_num: int, output_prefix: Path) -> list[Path]:
        """Extract embedded images for a page using the active reader handle."""
        from pdf_goon.models import PdfGoonError

        if self.reader is None:
            raise RuntimeError("PypdfExtractSession is closed or uninitialized")
        try:
            page = self.reader.pages[page_num - 1]
            return _extract_page_images_from_page(page, page_num, output_prefix)
        except Exception as exc:
            raise PdfGoonError(
                f"Failed to extract images from page {page_num} with pypdf session: {exc}"
            ) from exc

    def close(self) -> None:
        """Close open file and reader handles."""
        if hasattr(self, "_f") and self._f is not None:
            try:
                self._f.close()
            except Exception:
                pass
            self._f = None
        self.reader = None

    def __enter__(self) -> PypdfExtractSession:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


def _get_worker_cmd() -> list[str]:
    import sys

    if getattr(sys, "frozen", False):
        return [sys.executable, "--_render_worker"]
    return [sys.executable, "-m", "pdf_goon._render_worker"]


def render_page(
    pdf_path: Path,
    page_num: int,
    output_prefix: Path,
    dpi: float,
    page_info: PageInfo,
    *,
    run: Callable[[list[str]], str] = run_command,
) -> list[Path]:
    """Render a PDF page via the standalone worker subprocess."""
    from pdf_goon.models import PdfGoonError, SubprocessError

    out_file = output_prefix.with_suffix(".png")
    if out_file.name == output_prefix.name:
        out_file = output_prefix.parent / f"{output_prefix.name}.png"

    cmd = _get_worker_cmd() + [
        str(pdf_path),
        str(page_num),
        str(dpi),
        str(out_file),
    ]

    try:
        run(cmd)
    except SubprocessError as exc:
        raise PdfGoonError(
            f"Failed to render page {page_num} with pypdfium2: {exc.stderr}"
        ) from exc

    return [out_file]


def _chunk_tasks(tasks: list[dict], chunk_count: int) -> list[list[dict]]:
    """Partition tasks into approximately equal-sized chunks."""
    k = max(1, min(chunk_count, len(tasks)))
    return [tasks[i::k] for i in range(k) if tasks[i::k]]


def _execute_render_worker_chunk(
    pdf_path: Path,
    chunk: list[dict],
    run: Callable[[list[str]], str],
) -> None:
    """Execute a single batch worker subprocess for a tasks chunk."""
    import json
    import tempfile
    from pdf_goon.models import PdfGoonError, SubprocessError

    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(chunk, f)
        tasks_file = Path(f.name)

    cmd = _get_worker_cmd() + [
        "--batch",
        str(pdf_path),
        str(tasks_file),
    ]

    try:
        run(cmd)
    except SubprocessError as exc:
        raise PdfGoonError(
            f"Failed to batch render pages with pypdfium2: {exc.stderr}"
        ) from exc
    finally:
        try:
            tasks_file.unlink(missing_ok=True)
        except Exception:
            pass


def render_batch(
    pdf_path: Path,
    tasks: list[dict],
    *,
    max_workers: int = 1,
    run: Callable[[list[str]], str] = run_command,
) -> list[Path]:
    """Render multiple PDF pages with optional multi-worker subprocess parallelism."""
    if not tasks:
        return []

    workers = max(1, min(max_workers, len(tasks)))
    if workers <= 1 or len(tasks) <= 2:
        _execute_render_worker_chunk(pdf_path, tasks, run)
    else:
        from concurrent.futures import ThreadPoolExecutor

        chunks = _chunk_tasks(tasks, workers)
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
            futures = [
                executor.submit(_execute_render_worker_chunk, pdf_path, chunk, run)
                for chunk in chunks
            ]
            for f in futures:
                f.result()

    return [Path(t["out"]) for t in tasks]
