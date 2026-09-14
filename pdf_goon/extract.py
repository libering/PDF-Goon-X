"""Image extraction and page rendering."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pdf_goon.models import PageInfo
from pdf_goon.tools import run_command


def extract_images(
    pdf_path: Path,
    page_num: int,
    output_prefix: Path,
) -> list[Path]:
    """Extract embedded images from a single PDF page using pypdf."""
    from pdf_goon.models import PdfGoonError

    try:
        import pypdf

        output_paths = []
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page = reader.pages[page_num - 1]

            for img_idx, img_file in enumerate(page.images):
                suffix = Path(img_file.name).suffix.lower()
                if suffix == ".jpeg":
                    suffix = ".jpg"
                if suffix not in (".png", ".jpg"):
                    suffix = ".png"

                out_path = (
                    output_prefix.parent / f"{output_prefix.name}-{img_idx:03d}{suffix}"
                )

                # pypdf's img_file.data for JPEGs is valid DCTDecode bytes.
                # However, for FlateDecode (PNG), it might be raw zlib bytes instead of a valid PNG file.
                # To guarantee valid image files, we save non-JPEGs using PIL.
                if suffix == ".jpg":
                    with open(out_path, "wb") as out_f:
                        out_f.write(img_file.data)
                else:
                    # Save as PNG using the PIL Image object to construct valid headers
                    pil_image = img_file.image
                    if pil_image is None:
                        raise ValueError(
                            f"PIL image unavailable for image {img_idx} on page {page_num}"
                        )
                    pil_image.save(out_path, format="PNG")

                output_paths.append(out_path)

        return sorted(output_paths)
    except Exception as exc:
        raise PdfGoonError(
            f"Failed to extract images from page {page_num} with pypdf: {exc}"
        ) from exc


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
    import sys
    from pdf_goon.models import PdfGoonError, SubprocessError

    out_file = output_prefix.with_suffix(".png")
    if out_file.name == output_prefix.name:
        out_file = output_prefix.parent / f"{output_prefix.name}.png"

    cmd = [
        sys.executable,
        "-m",
        "pdf_goon._render_worker",
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
