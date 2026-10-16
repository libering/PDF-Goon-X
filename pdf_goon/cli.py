"""pdf_goon.cli — Thin CLI: argparse → Config → process() → exit code."""

from __future__ import annotations

import argparse
import logging
import sys

import pdf_goon
from pdf_goon.models import VERSION, PdfGoonError

DESCRIPTION = (
    "Proper(ish) PDF ripping tool. "
    "Extracts raw images or renders the layout if necessary."
)


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with v1.0.1-compatible flags."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        epilog=f"Version {VERSION} | Credits: Uses pypdf, pypdfium2, and Pingo.exe. | Author: Dnkz",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Target directory to process (default: current directory)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show per-page processing details (Extraction vs Rendering)",
    )
    parser.add_argument(
        "-r",
        "--replace",
        action="store_true",
        help="Move processed PDF to Recycle Bin (local) or a central '!delete' folder (network/recursive)",
    )
    parser.add_argument(
        "-recursive",
        "--include-subdirectories",
        action="store_true",
        help="Recursively search all subdirectories for PDF files",
    )
    parser.add_argument(
        "-dpi-text",
        type=int,
        metavar="DPI",
        default=400,
        help="DPI for pages without images or with icons only (default: 400)",
    )
    parser.add_argument(
        "-min-w",
        type=int,
        default=500,
        metavar="PX",
        help="Ignore embedded images narrower than this and use -dpi-text instead (default: 500)",
    )
    parser.add_argument(
        "--no-optimization",
        action="store_false",
        dest="optimize",
        help="Disable lossless image optimization",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show all Poppler syntax warnings and errors, and additional info. Includes -v",
    )
    parser.add_argument(
        "--force-render",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--keep-blank",
        action="store_true",
        help="Render blank pages at dpi_text instead of skipping them",
    )
    parser.add_argument(
        "--margin-tolerance",
        type=float,
        default=3.0,
        metavar="PTS",
        help="Margin tolerance in points for full-page bleed detection (default: 3.0)",
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="Wait for user input before exiting (prevents console window auto-closing)",
    )
    parser.add_argument(
        "--log-file",
        nargs="?",
        const="pdf_goon_debug.log",
        default=None,
        metavar="FILE",
        help="Write diagnostic logs to specified file (default: pdf_goon_debug.log)",
    )
    parser.set_defaults(optimize=True)
    return parser


def main() -> None:
    """Parse CLI arguments, call process(), print results, exit."""
    # Internal render worker dispatch (supports PyInstaller frozen binary)
    if len(sys.argv) > 1 and sys.argv[1] == "--_render_worker":
        from pdf_goon._render_worker import main as worker_main

        worker_main(sys.argv[2:])
        sys.exit(0)

    # Banner
    print("=" * 60)
    print(f"PDF-Goon v{VERSION}")
    print(DESCRIPTION)
    print("=" * 60)

    # Parse
    parser = _build_parser()
    args = parser.parse_args()

    # Configure logging: diagnostic output goes to stderr and optional log file
    log_level = (
        logging.DEBUG
        if args.debug
        else (logging.INFO if args.verbose else logging.WARNING)
    )
    log_file = args.log_file or ("pdf_goon_debug.log" if args.debug else None)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        try:
            file_h = logging.FileHandler(log_file, mode="w", encoding="utf-8")
            file_h.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            )
            handlers.append(file_h)
        except Exception as e:
            sys.stderr.write(f"Warning: Could not open log file {log_file}: {e}\n")

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        handlers=handlers,
        force=True,
    )

    if args.debug:
        import platform

        logger = logging.getLogger("pdf_goon")
        logger.debug("=== PDF-Goon Debug Environment ===")
        logger.debug("Version: %s", VERSION)
        logger.debug("Python: %s", sys.version.replace("\n", " "))
        logger.debug("Platform: %s", platform.platform())
        logger.debug("Executable: %s", sys.executable)
        logger.debug("CLI Arguments: %s", sys.argv)
        logger.debug("==================================")

    # Configuration summary
    print(
        f"Configuration => Path: '{args.path}' "
        f"| Recursive (include subdirectories): {args.include_subdirectories} "
        f"| Replace: {args.replace} "
        f"| DPI for Textpages: {args.dpi_text} "
        f"| Min-Width: {args.min_w}px "
        f"| Lossless Optimization: {args.optimize}"
    )
    print("=" * 60)

    # Delegate to public API and handle errors
    exit_code = 0
    try:
        pdf_goon.process(
            path=args.path,
            verbose=args.verbose,
            replace=args.replace,
            optimize=args.optimize,
            dpi_text=args.dpi_text,
            min_width=args.min_w,
            recursive=args.include_subdirectories,
            force_render=args.force_render,
            debug=args.debug,
            keep_blank=args.keep_blank,
            margin_tolerance=args.margin_tolerance,
        )
    except PdfGoonError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc(file=sys.stderr)
        exit_code = 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc(file=sys.stderr)
        exit_code = 2
    else:
        print("All Done.")
    finally:
        if args.pause:
            try:
                input("\n[Debug] 請按 Enter 鍵結束程式 (Press Enter to exit)...")
            except (EOFError, KeyboardInterrupt):
                pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
