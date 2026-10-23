# tests.test_core_finalize — Tests for finalization naming, masks, and collisions in pdf_goon.core

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.core import _finalize_page_files, process_single_pdf
from pdf_goon.models import (
    Config,
    PageDecision,
    PageInfo,
    ProcessingMode,
    make_config,
)

_PATCH_GET_PAGE_COUNT = "pdf_goon.core.get_page_count"
_PATCH_GET_IMAGE_DATA = "pdf_goon.core.get_image_data"
_PATCH_GET_PAGE_INFO = "pdf_goon.core.get_page_info"
_PATCH_DECIDE_MODE = "pdf_goon.core.decide_processing_mode"
_PATCH_OPTIMIZE_IMAGE = "pdf_goon.core.optimize_image"
_PATCH_RENDER_PAGE = "pdf_goon.core.render_page"


def _make_config(tmp_path: Path, **overrides: object) -> Config:
    defaults = {
        "path": str(tmp_path),
        "verbose": False,
        "replace": False,
        "optimize": False,
        "recursive": False,
    }
    defaults.update(overrides)
    return make_config(**defaults)


def _run_single_pdf_render_capture(tmp_path: Path, config: Config) -> Path:
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")
    render_prefix_used: list[Path] = []

    def capture_render_prefix(
        pdf_path: Path,
        page_num: int,
        output_prefix: Path,
        dpi: float,
        page_info: object,
        pdf_data: bytes | None = None,
    ) -> list[Path]:
        render_prefix_used.append(output_prefix)
        out_file = output_prefix.parent / f"{output_prefix.name}.png"
        out_file.write_bytes(b"fake png")
        return [out_file]

    with (
        patch(_PATCH_GET_PAGE_COUNT, return_value=1),
        patch(_PATCH_GET_IMAGE_DATA, return_value=([], [], False)),
        patch(_PATCH_GET_PAGE_INFO, return_value=PageInfo(612.0, 792.0)),
        patch(
            _PATCH_DECIDE_MODE,
            return_value=PageDecision(ProcessingMode.RENDER, 150, "force render"),
        ),
        patch(_PATCH_RENDER_PAGE, side_effect=capture_render_prefix),
        patch(_PATCH_OPTIMIZE_IMAGE, return_value=0),
    ):
        process_single_pdf(pdf_file, workspace=tmp_path, config=config)

    assert len(render_prefix_used) == 1
    return render_prefix_used[0]


class TestRenderPrefixCollision:
    """Tests for bug B2 — render file prefix glob collision with extraction prefix."""

    def test_render_prefix_not_caught_by_extraction_glob(self, tmp_path: Path) -> None:
        """Render file prefix must NOT start with extraction prefix."""
        page = 1
        config = _make_config(tmp_path)
        render_prefix = _run_single_pdf_render_capture(tmp_path, config)

        extraction_prefix_name = f"page_{page}_tmp"
        render_name = render_prefix.name
        assert not render_name.startswith(extraction_prefix_name), (
            f"Render prefix '{render_name}' starts with extraction prefix "
            f"'{extraction_prefix_name}' — glob collision!"
        )


class TestSubImageIndexRegex:
    r"""Tests for bug B1 — sub-image index must use the TAIL dash-number."""

    def test_multi_image_page_uses_tail_index(self, tmp_path: Path) -> None:
        r"""Sub-image naming uses the LAST dash-number (file index), not the first."""
        workspace = tmp_path / "work"
        workspace.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        file_a = workspace / "page_1_tmp-3-000.png"
        file_b = workspace / "page_1_tmp-3-001.png"
        file_a.write_bytes(b"fake png A")
        file_b.write_bytes(b"fake png B")

        config = _make_config(tmp_path)
        _finalize_page_files(
            generated_files=[file_a, file_b],
            mask_indices=[],
            was_rendered=False,
            page=1,
            output_dir=output_dir,
            config=config,
        )

        output_files = sorted(f.name for f in output_dir.iterdir())
        assert "001.png" in output_files
        assert "001_001.png" in output_files


def _assert_rendered_output_present(work_dir: Path, page: int, suffix: str) -> None:
    workspace = work_dir / "work"
    workspace.mkdir()
    output_dir = work_dir / "output"
    output_dir.mkdir()

    render_file = workspace / f"render_{page}_tmp{suffix}"
    render_file.write_bytes(b"\x89PNG fake image data")
    config = _make_config(work_dir)

    result = _finalize_page_files(
        generated_files=[render_file],
        mask_indices=[],
        was_rendered=True,
        page=page,
        output_dir=output_dir,
        config=config,
    )
    expected_name = f"{page:03d}_r{suffix}"
    assert len(result) >= 1
    assert result[0].name == expected_name
    assert result[0].exists()


class TestRenderedPagesOutputLoss:
    """Bug condition exploration: RENDER path files silently discarded."""

    @settings(max_examples=50)
    @given(
        page=st.integers(min_value=1, max_value=999),
        suffix=st.sampled_from([".png", ".jpg", ".jpeg"]),
    )
    def test_render_path_files_included_in_output(
        self, page: int, suffix: str
    ) -> None:
        """RENDER path files (pdftocairo -singlefile format) must be included in output."""
        work_dir = Path(tempfile.mkdtemp(prefix="pbt_render_"))
        try:
            _assert_rendered_output_present(work_dir, page, suffix)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


def _assert_extract_non_mask_moved(
    work_dir: Path, page: int, suffix: str, num_images: int
) -> None:
    workspace = work_dir / "work"
    workspace.mkdir()
    output_dir = work_dir / "output"
    output_dir.mkdir()

    generated_files: list[Path] = []
    for i in range(num_images):
        fname = workspace / f"page_{page}_tmp-{i:03d}{suffix}"
        fname.write_bytes(b"\x89PNG fake image data")
        generated_files.append(fname)

    config = _make_config(work_dir)
    result = _finalize_page_files(
        generated_files=generated_files,
        mask_indices=[],
        was_rendered=False,
        page=page,
        output_dir=output_dir,
        config=config,
    )
    assert len(result) == num_images
    for f in result:
        assert f.exists()
        assert f.parent == output_dir


def _assert_extract_mask_deleted(
    work_dir: Path, page: int, suffix: str, num_images: int
) -> None:
    workspace = work_dir / "work"
    workspace.mkdir()
    output_dir = work_dir / "output"
    output_dir.mkdir()

    generated_files: list[Path] = []
    for i in range(num_images):
        fname = workspace / f"page_{page}_tmp-{i:03d}{suffix}"
        fname.write_bytes(b"\x89PNG fake image data")
        generated_files.append(fname)

    mask_indices = ["000"]
    config = _make_config(work_dir)
    result = _finalize_page_files(
        generated_files=generated_files,
        mask_indices=mask_indices,
        was_rendered=False,
        page=page,
        output_dir=output_dir,
        config=config,
    )
    expected_output = num_images - len(mask_indices)
    assert len(result) == expected_output
    masked_file = generated_files[0]
    assert not masked_file.exists()


def _assert_extract_sub_image_naming(work_dir: Path, page: int, suffix: str) -> None:
    workspace = work_dir / "work"
    workspace.mkdir()
    output_dir = work_dir / "output"
    output_dir.mkdir()

    file_a = workspace / f"page_{page}_tmp-000{suffix}"
    file_b = workspace / f"page_{page}_tmp-001{suffix}"
    file_a.write_bytes(b"\x89PNG fake image A")
    file_b.write_bytes(b"\x89PNG fake image B")

    config = _make_config(work_dir)
    result = _finalize_page_files(
        generated_files=[file_a, file_b],
        mask_indices=[],
        was_rendered=False,
        page=page,
        output_dir=output_dir,
        config=config,
    )

    assert len(result) == 2
    names = {f.name for f in result}
    base_name = f"{page:03d}{suffix}"
    sub_name = f"{page:03d}_001{suffix}"
    assert base_name in names
    assert sub_name in names


class TestExtractPathPreservation:
    """Preservation: EXTRACT path behavior is completely unchanged after fix."""

    @settings(max_examples=50, deadline=None)
    @given(
        page=st.integers(min_value=1, max_value=999),
        suffix=st.sampled_from([".png", ".jpg", ".jpeg"]),
        num_images=st.integers(min_value=1, max_value=5),
    )
    def test_extract_path_non_mask_files_moved_to_output(
        self, page: int, suffix: str, num_images: int
    ) -> None:
        """EXTRACT path: non-mask files are moved to output_dir with correct naming."""
        work_dir = Path(tempfile.mkdtemp(prefix=f"pbt_preserve_{uuid4().hex}_"))
        try:
            _assert_extract_non_mask_moved(work_dir, page, suffix, num_images)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    @settings(max_examples=50, deadline=None)
    @given(
        page=st.integers(min_value=1, max_value=999),
        suffix=st.sampled_from([".png", ".jpg", ".jpeg"]),
        num_images=st.integers(min_value=2, max_value=6),
        mask_count=st.integers(min_value=1, max_value=1),
    )
    def test_extract_path_mask_files_are_deleted(
        self, page: int, suffix: str, num_images: int, mask_count: int
    ) -> None:
        """EXTRACT path: files whose index is in mask_indices are deleted, not in output."""
        work_dir = Path(tempfile.mkdtemp(prefix=f"pbt_mask_{uuid4().hex}_"))
        try:
            _assert_extract_mask_deleted(work_dir, page, suffix, num_images)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def test_extract_path_non_image_extensions_are_skipped(
        self, tmp_path: Path
    ) -> None:
        """EXTRACT path: files with non-image extensions are skipped."""
        workspace = tmp_path / "work"
        workspace.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        img_file = workspace / "page_1_tmp-000.png"
        txt_file = workspace / "page_1_tmp-001.txt"
        pdf_file = workspace / "page_1_tmp-002.pdf"
        img_file.write_bytes(b"\x89PNG fake image data")
        txt_file.write_bytes(b"not an image")
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        config = _make_config(tmp_path)
        result = _finalize_page_files(
            generated_files=[img_file, txt_file, pdf_file],
            mask_indices=[],
            was_rendered=False,
            page=1,
            output_dir=output_dir,
            config=config,
        )

        assert len(result) == 1
        assert result[0].suffix == ".png"

    @settings(max_examples=30)
    @given(
        page=st.integers(min_value=1, max_value=999),
        suffix=st.sampled_from([".png", ".jpg", ".jpeg"]),
    )
    def test_extract_path_sub_image_naming(self, page: int, suffix: str) -> None:
        """EXTRACT path: multiple files per page get sub-image naming."""
        work_dir = Path(tempfile.mkdtemp(prefix="pbt_subimg_"))
        try:
            _assert_extract_sub_image_naming(work_dir, page, suffix)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
