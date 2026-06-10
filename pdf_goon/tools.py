"""Tool resolution and subprocess execution for pdf_goon."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from pdf_goon.models import POPPLER_TOOLS, SubprocessError

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT: int = 300  # 5 minutes — prevents hanging on malicious PDFs

# Only these tools may be resolved from the local directory (binary planting protection)
_ALLOWED_LOCAL_TOOLS: frozenset[str] = frozenset({
    "pdfimages", "pdfimages.exe",
    "pdfinfo", "pdfinfo.exe",
    "pdftocairo", "pdftocairo.exe",
    "pingo", "pingo.exe",
    "oxipng", "oxipng.exe",
    "jpegoptim", "jpegoptim.exe",
})


def get_tool_path(tool_name: str) -> str:
    """Resolve path to a CLI tool (PyInstaller bundle, local directory, or PATH)."""
    # 1. PyInstaller bundle via sys._MEIPASS
    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / tool_name
        if bundled.exists():
            return str(bundled)

    # 2. Local directory next to this file — only for allowed tools
    if tool_name in _ALLOWED_LOCAL_TOOLS:
        local = Path(__file__).parent / tool_name
        if local.exists():
            return str(local)

    # 3. Fall back to system PATH via shutil.which
    found = shutil.which(tool_name)
    if found:
        return found

    # Return bare name as last resort (let subprocess raise if missing)
    return tool_name


def run_command(cmd: list[str], *, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Execute a subprocess and return stdout, filtering irrelevant Poppler warnings."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SubprocessError(
            tool=cmd[0],
            exit_code=-1,
            stderr=f"Process timed out after {timeout}s",
        ) from exc

    # Log raw stderr at DEBUG level for diagnostics
    if result.stderr and result.stderr.strip():
        logger.debug("stderr from %s:\n%s", cmd[0], result.stderr.rstrip())

    # Filter irrelevant Poppler noise from stderr
    if result.returncode != 0:
        filtered = _filter_stderr(result.stderr)
        raise SubprocessError(
            tool=cmd[0],
            exit_code=result.returncode,
            stderr=filtered,
        )

    return result.stdout


def check_poppler_available() -> list[str]:
    """Return list of missing required Poppler tools (empty means all present)."""
    return [tool for tool in POPPLER_TOOLS if shutil.which(tool) is None]


def check_optimizer_available(platform: str) -> bool:
    """Check if optimization tools are available for the given platform."""
    if platform == "nt":
        return shutil.which("pingo") is not None

    # posix: need at least one of oxipng or jpegoptim
    return (
        shutil.which("oxipng") is not None
        or shutil.which("jpegoptim") is not None
    )


def _filter_stderr(stderr: str) -> str:
    """Remove irrelevant Poppler syntax warnings from stderr output."""
    if not stderr or not stderr.strip():
        return ""

    lines = stderr.splitlines()
    filtered = [
        line
        for line in lines
        if line.strip()
        and "Syntax Warning:" not in line
        and "Syntax Error:" not in line
    ]
    return "\n".join(filtered)
