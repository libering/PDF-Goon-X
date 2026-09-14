"""Tool resolution and subprocess execution for pdf_goon."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from pdf_goon.models import SubprocessError

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT: int = 300  # 5 minutes — prevents hanging on malicious PDFs

# Only these tools may be resolved from the local directory (binary planting protection)
_ALLOWED_LOCAL_TOOLS: frozenset[str] = frozenset(
    {
        "pingo",
        "pingo.exe",
        "oxipng",
        "oxipng.exe",
        "jpegoptim",
        "jpegoptim.exe",
    }
)


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
    """Execute a subprocess and return stdout."""
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
    except FileNotFoundError as exc:
        # Executable not found on PATH — wrap as SubprocessError for uniform handling
        raise SubprocessError(
            tool=cmd[0],
            exit_code=-1,
            stderr=f"Executable not found: {cmd[0]}",
        ) from exc

    # Log raw stderr at DEBUG level for diagnostics
    if result.stderr and result.stderr.strip():
        logger.debug("stderr from %s:\n%s", cmd[0], result.stderr.rstrip())

    if result.returncode != 0:
        raise SubprocessError(
            tool=cmd[0],
            exit_code=result.returncode,
            stderr=result.stderr,
        )

    return result.stdout


def check_optimizer_available(platform: str) -> bool:
    """Check if optimization tools are available for the given platform."""
    if platform == "nt":
        return get_tool_path("pingo") != "pingo" or shutil.which("pingo") is not None

    # posix: need at least one of oxipng or jpegoptim
    return (
        get_tool_path("oxipng") != "oxipng"
        or shutil.which("oxipng") is not None
        or get_tool_path("jpegoptim") != "jpegoptim"
        or shutil.which("jpegoptim") is not None
    )
