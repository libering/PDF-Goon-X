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
        epilog=f"Version {VERSION} | Credits: Uses Poppler-utils and Pingo.exe. | Author: Dnkz",
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
    parser.set_defaults(optimize=True)
    return parser


def main() -> None:
    """Parse CLI arguments, call process(), print results, exit."""
    # Banner
    print("=" * 60)
    print(f"PDF-Goon v{VERSION}")
    print(DESCRIPTION)
    print("=" * 60)

    # Parse
    parser = _build_parser()
    args = parser.parse_args()

    # Configure logging: diagnostic output goes to stderr
    log_level = (
        logging.DEBUG
        if args.debug
        else (logging.INFO if args.verbose else logging.WARNING)
    )
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stderr,
    )

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
        )
    except PdfGoonError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(2)

    print("All Done.")
    sys.exit(0)


if __name__ == "__main__":
    main()
