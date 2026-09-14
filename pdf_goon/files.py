"""File operations: unique paths, cleanup, trash, workspace."""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import tempfile
import time
from collections.abc import Generator
from pathlib import Path

logger = logging.getLogger(__name__)


def get_unique_path(path: Path, is_dir: bool = False) -> Path:
    """Return a non-colliding path by appending (1), (2), etc."""
    if not path.exists():
        return path

    parent = path.parent
    if is_dir:
        stem = path.name
        suffix = ""
    else:
        stem = path.stem
        suffix = path.suffix

    counter = 1
    while True:
        new_name = f"{stem} ({counter}){suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1


def is_network_path(path: Path) -> bool:
    """Check if path is on a network drive (UNC or mapped network on Windows)."""
    if os.name != "nt":
        return False

    resolved = path.resolve()
    if str(resolved).startswith("\\\\"):
        return True

    import ctypes

    drive_letter = resolved.anchor
    return bool(
        drive_letter and ctypes.windll.kernel32.GetDriveTypeW(drive_letter) == 4
    )


def _trash_windows(pdf_path: Path) -> bool:
    """Attempt to move a file to the Windows Recycle Bin via SHFileOperationW."""
    try:
        import ctypes
        import ctypes.wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.wintypes.HWND),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x0040
        FOF_NOCONFIRMATION = 0x0010
        FOF_NOERRORUI = 0x0400
        FOF_SILENT = 0x0004

        # pFrom must be double-null terminated
        file_path = str(pdf_path) + "\0"

        file_op = SHFILEOPSTRUCTW()
        file_op.hwnd = None
        file_op.wFunc = FO_DELETE
        file_op.pFrom = file_path
        file_op.pTo = None
        file_op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
        file_op.fAnyOperationsAborted = False
        file_op.hNameMappings = None
        file_op.lpszProgressTitle = None

        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(file_op))
        return bool(result == 0)
    except Exception:
        return False


def _trash_freedesktop(pdf_path: Path) -> bool:
    """Attempt to move a file to the freedesktop trash (~/.local/share/Trash/)."""
    try:
        trash_dir = Path.home() / ".local" / "share" / "Trash"
        files_dir = trash_dir / "files"
        info_dir = trash_dir / "info"

        files_dir.mkdir(parents=True, exist_ok=True)
        info_dir.mkdir(parents=True, exist_ok=True)

        # Generate a unique name in the trash
        trash_name = pdf_path.name
        dest = files_dir / trash_name
        counter = 1
        while dest.exists():
            trash_name = f"{pdf_path.stem} ({counter}){pdf_path.suffix}"
            dest = files_dir / trash_name
            counter += 1

        # Write .trashinfo file
        deletion_date = time.strftime("%Y-%m-%dT%H:%M:%S")
        info_content = (
            f"[Trash Info]\nPath={pdf_path.resolve()}\nDeletionDate={deletion_date}\n"
        )
        info_file = info_dir / f"{trash_name}.trashinfo"
        info_file.write_text(info_content, encoding="utf-8")

        # Move the file
        shutil.move(str(pdf_path), str(dest))
        return True
    except Exception:
        return False


def trash_or_move(pdf_path: Path, delete_dir: Path | None = None) -> None:
    """Move PDF to trash (platform-native) or to a !delete folder as fallback."""
    # Try platform-native trash first
    if os.name == "nt":
        if _trash_windows(pdf_path):
            return
    else:
        if _trash_freedesktop(pdf_path):
            return

    # Fallback: move to delete directory
    target_dir = delete_dir if delete_dir is not None else (pdf_path.parent / "!delete")
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = get_unique_path(target_dir / pdf_path.name, is_dir=False)
        shutil.move(str(pdf_path), str(dest))
    except Exception as exc:
        logger.warning("Failed to move %s to delete folder: %s", pdf_path, exc)


@contextlib.contextmanager
def workspace_context(base_dir: Path | None = None) -> Generator[Path, None, None]:
    """Context manager that creates a temp workspace and guarantees cleanup."""
    parent = str(base_dir) if base_dir is not None else None
    workspace = Path(tempfile.mkdtemp(prefix="pdf_goon_", dir=parent))
    try:
        yield workspace
    finally:
        try:
            shutil.rmtree(workspace)
        except Exception as exc:
            logger.warning("Failed to clean up workspace %s: %s", workspace, exc)
