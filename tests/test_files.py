# tests.test_files — Tests for pdf_goon.files

import os
import shutil
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.files import get_unique_path


# Feature: pdf-goon-refactor, Property 8: Unique path generation never collides with existing paths

_filename_alphabet = st.characters(whitelist_categories=("L", "N"))
_filenames = st.text(alphabet=_filename_alphabet, min_size=1, max_size=10)
_extensions = st.sampled_from([".pdf", ".png", ".txt"])


@settings(max_examples=100)
@given(filename=_filenames, ext=_extensions)
def test_unique_path_returns_input_when_no_collision(filename: str, ext: str) -> None:
    """If the input path does not exist, get_unique_path returns it unchanged.

    **Validates: Requirements 10.1**
    """
    tmp_dir = tempfile.mkdtemp(prefix="pbt_files_")
    try:
        input_path = Path(tmp_dir) / f"{filename}{ext}"
        result = get_unique_path(input_path)
        assert result == input_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@settings(max_examples=100)
@given(
    filename=_filenames,
    ext=_extensions,
    num_existing=st.integers(min_value=1, max_value=5),
)
def test_unique_path_never_collides_with_existing(
    filename: str, ext: str, num_existing: int
) -> None:
    """If the input path exists, get_unique_path returns a different, non-existing path.

    **Validates: Requirements 10.1**
    """
    tmp_dir = tempfile.mkdtemp(prefix="pbt_files_")
    try:
        base_path = Path(tmp_dir) / f"{filename}{ext}"

        # Create the base file and some numbered variants to simulate collisions
        base_path.touch()
        for i in range(1, num_existing):
            variant = Path(tmp_dir) / f"{filename} ({i}){ext}"
            variant.touch()

        result = get_unique_path(base_path)

        # The result must not collide with any existing path
        assert not result.exists()
        # The result must differ from the original since it already exists
        assert result != base_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# Feature: pdf-goon-refactor, Property 6: Workspace cleanup is guaranteed regardless of outcome

from pdf_goon.files import workspace_context


def test_workspace_cleanup_on_success(tmp_path: Path) -> None:
    """Workspace directory is removed after successful execution.

    **Validates: Requirements 13.1, 13.2**
    """
    with workspace_context(base_dir=tmp_path) as workspace:
        assert workspace.exists()
        workspace_path = workspace

    assert not workspace_path.exists()


def test_workspace_cleanup_on_expected_error(tmp_path: Path) -> None:
    """Workspace directory is removed when an expected error is raised inside.

    **Validates: Requirements 13.1, 13.2**
    """
    workspace_path: Path | None = None
    try:
        with workspace_context(base_dir=tmp_path) as workspace:
            workspace_path = workspace
            assert workspace.exists()
            raise ValueError("simulated expected error")
    except ValueError:
        pass

    assert workspace_path is not None
    assert not workspace_path.exists()


def test_workspace_cleanup_on_unexpected_exception(tmp_path: Path) -> None:
    """Workspace directory is removed when an unexpected exception is raised inside.

    **Validates: Requirements 13.1, 13.2**
    """
    workspace_path: Path | None = None
    try:
        with workspace_context(base_dir=tmp_path) as workspace:
            workspace_path = workspace
            assert workspace.exists()
            raise RuntimeError("simulated unexpected crash")
    except RuntimeError:
        pass

    assert workspace_path is not None
    assert not workspace_path.exists()


# --- Unit Tests for files.py (Task 8.4) ---

from unittest.mock import patch

from pdf_goon.files import is_network_path, trash_or_move


# --- get_unique_path unit tests ---


def test_get_unique_path_no_collision(tmp_path: Path) -> None:
    """When the path does not exist, returns it unchanged.

    **Validates: Requirements 10.1**
    """
    target = tmp_path / "report.pdf"
    # Don't create the file — no collision
    result = get_unique_path(target)
    assert result == target


def test_get_unique_path_single_collision(tmp_path: Path) -> None:
    """When the path exists, returns path with (1) suffix.

    **Validates: Requirements 10.1**
    """
    target = tmp_path / "report.pdf"
    target.touch()

    result = get_unique_path(target)
    assert result == tmp_path / "report (1).pdf"
    assert not result.exists()


def test_get_unique_path_multiple_collisions(tmp_path: Path) -> None:
    """When path and (1) both exist, skips to (2).

    **Validates: Requirements 10.1**
    """
    target = tmp_path / "report.pdf"
    target.touch()
    (tmp_path / "report (1).pdf").touch()

    result = get_unique_path(target)
    assert result == tmp_path / "report (2).pdf"
    assert not result.exists()


def test_get_unique_path_directory_mode(tmp_path: Path) -> None:
    """In directory mode (is_dir=True), appends (1) to directory name.

    **Validates: Requirements 10.1**
    """
    target = tmp_path / "output"
    target.mkdir()

    result = get_unique_path(target, is_dir=True)
    assert result == tmp_path / "output (1)"
    assert not result.exists()


# --- is_network_path unit tests ---


def test_is_network_path_unc_on_windows() -> None:
    """UNC path on Windows returns True.

    **Validates: Requirements 11.2**
    """
    with patch("pdf_goon.files.os.name", "nt"):
        # Patch Path.resolve to return a UNC-style path
        unc_path = Path("\\\\server\\share\\file.pdf")
        with patch.object(Path, "resolve", return_value=Path("\\\\server\\share\\file.pdf")):
            result = is_network_path(unc_path)
    assert result is True


def test_is_network_path_local_on_non_windows() -> None:
    """Local path on non-Windows returns False.

    **Validates: Requirements 11.2**
    """
    with patch("pdf_goon.files.os.name", "posix"):
        result = is_network_path(Path("/home/user/file.pdf"))
    assert result is False


# --- trash_or_move unit tests ---


def test_trash_or_move_fallback_to_delete_folder(tmp_path: Path) -> None:
    """When native trash fails, file is moved to !delete folder.

    **Validates: Requirements 11.2, 13.1**
    """
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_text("dummy content")

    with patch("pdf_goon.files._trash_windows", return_value=False), \
         patch("pdf_goon.files._trash_freedesktop", return_value=False):
        trash_or_move(pdf_file)

    # Original file should be gone
    assert not pdf_file.exists()
    # File should be in !delete folder
    delete_dir = tmp_path / "!delete"
    assert delete_dir.exists()
    assert (delete_dir / "test.pdf").exists()


def test_trash_or_move_explicit_delete_dir(tmp_path: Path) -> None:
    """With explicit delete_dir parameter, file is moved there.

    **Validates: Requirements 11.2, 13.1**
    """
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_text("dummy content")
    custom_dir = tmp_path / "my_trash"

    with patch("pdf_goon.files._trash_windows", return_value=False), \
         patch("pdf_goon.files._trash_freedesktop", return_value=False):
        trash_or_move(pdf_file, delete_dir=custom_dir)

    assert not pdf_file.exists()
    assert custom_dir.exists()
    assert (custom_dir / "test.pdf").exists()
