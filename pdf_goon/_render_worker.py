"""Standalone render worker: renders a single PDF page via pypdfium2."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def run_batch_render(pdf_path: Path, tasks: list[dict]) -> None:
    """Load PDF document once with pypdfium2 and render all requested pages sequentially."""
    import pypdfium2 as pdfium

    pdf_bytes = pdf_path.read_bytes()
    pdf = pdfium.PdfDocument(pdf_bytes)
    had_error = False
    try:
        for task in tasks:
            page_num = int(task["page"])
            dpi = float(task["dpi"])
            output_path = Path(task["out"])
            try:
                page = pdf[page_num - 1]
                bitmap = page.render(scale=dpi / 72.0)
                pil_image = bitmap.to_pil()
                pil_image.save(output_path)
                page.close()
            except Exception as e:
                had_error = True
                sys.stderr.write(f"Error rendering page {page_num}: {e}\n")
    finally:
        pdf.close()
    if had_error:
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args, render page(s), write PNG."""
    args = sys.argv[1:] if argv is None else argv

    # Batch mode: --batch <pdf_path> <tasks_json_file_or_string>
    if len(args) == 3 and args[0] == "--batch":
        try:
            pdf_path = Path(args[1])
            tasks_arg = args[2]
            p = Path(tasks_arg)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
            else:
                tasks = json.loads(tasks_arg)
            run_batch_render(pdf_path, tasks)
        except Exception as exc:
            sys.stderr.write(f"Batch render error: {exc}\n")
            sys.exit(1)
        sys.exit(0)

    if len(args) != 4:
        sys.stderr.write(
            "Usage: _render_worker <pdf_path> <page_num> <dpi> <output_path>\n"
        )
        sys.exit(1)

    try:
        pdf_path = Path(args[0])
        page_num = int(args[1])
        dpi = float(args[2])
        output_path = Path(args[3])
    except (ValueError, TypeError) as exc:
        sys.stderr.write(f"Argument error: {exc}\n")
        sys.exit(1)

    try:
        import pypdfium2 as pdfium

        # Read bytes from disk to avoid Windows file lock sharing issues
        pdf_bytes = pdf_path.read_bytes()
        pdf = pdfium.PdfDocument(pdf_bytes)
        try:
            page = pdf[page_num - 1]
            bitmap = page.render(scale=dpi / 72.0)
            pil_image = bitmap.to_pil()
            pil_image.save(output_path)
            page.close()
        finally:
            pdf.close()
    except Exception as exc:
        sys.stderr.write(f"Render error: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
