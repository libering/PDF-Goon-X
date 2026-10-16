"""pdf_goon.debug_entry — Dedicated entrypoint for pdf-goon-debug.exe.

Automatically enables debug diagnostics, verbose page analysis, automatic logfile
generation (pdf_goon_debug.log), and post-execution pause (preventing window auto-close
when drag-and-dropping files on Windows).
"""

from __future__ import annotations

import sys
from pdf_goon.cli import main


def run() -> None:
    # If invoked as an internal render worker subprocess, pass through untouched
    if len(sys.argv) > 1 and sys.argv[1] == "--_render_worker":
        main()
        return

    # For user execution (CLI or Explorer drag-and-drop), auto-inject debug flags
    # We prepend flags after sys.argv[0] so positional args (like dropped PDF files) stay at the end
    args = sys.argv[1:]

    injected: list[str] = []
    if "--debug" not in args:
        injected.append("--debug")
    if "-v" not in args and "--verbose" not in args:
        injected.append("-v")
    if "--pause" not in args:
        injected.append("--pause")
    if "--log-file" not in args:
        injected.extend(["--log-file", "pdf_goon_debug.log"])

    sys.argv = [sys.argv[0]] + injected + args
    main()


if __name__ == "__main__":
    run()
