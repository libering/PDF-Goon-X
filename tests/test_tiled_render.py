"""TDD unit tests for Tiled Render Engine."""

import json
from pathlib import Path
from PIL import Image, ImageChops
import pypdfium2 as pdfium
import pytest

from pdf_goon.models import PageInfo
from pdf_goon.render.tiler import (
    should_tile_render,
    calculate_tile_grid,
    render_page_tiled,
    TileInfo,
)


def test_calculate_tile_grid_dimension_and_edge_clamping():
    """1.1 Verify grid subdivision and dynamic edge truncation without pixel drift."""
    # Suppose total image size is 9000 x 5000, tile_size = 4096
    # Width chunks: [0, 4096), [4096, 8192), [8192, 9000) -> 3 cols
    # Height chunks: [0, 4096), [4096, 5000) -> 2 rows
    # Total tiles: 6
    grid, rows, cols = calculate_tile_grid(total_w=9000, total_h=5000, tile_size=4096)
    assert rows == 2
    assert cols == 3
    assert len(grid) == 6

    # Verify edge tile (row 1, col 2)
    edge_tile = grid[-1]
    assert edge_tile.row == 1
    assert edge_tile.col == 2
    assert edge_tile.x0 == 8192
    assert edge_tile.x1 == 9000
    assert edge_tile.w == 808
    assert edge_tile.y0 == 4096
    assert edge_tile.y1 == 5000
    assert edge_tile.h == 904


def test_should_tile_render_heuristics():
    """Verify dual-dimension threshold and force flag."""
    # 1. Normal A4 page (595 x 842 pts at 300 DPI -> ~2479 x 3508 px -> 8.7 MP)
    normal_page = PageInfo(width_pts=595.0, height_pts=842.0)
    assert should_tile_render(normal_page, dpi=300.0) is False

    # 2. Forced by flag
    assert should_tile_render(normal_page, dpi=300.0, force_tiles=True) is True

    # 3. Mega poster (>100 MP, e.g. 3000 x 3000 pts at 300 DPI -> 12500 x 12500 px -> 156.25 MP)
    mega_poster = PageInfo(width_pts=3000.0, height_pts=3000.0)
    assert should_tile_render(mega_poster, dpi=300.0) is True

    # 4. Long scroll / extreme single edge (>16,384 px)
    long_banner = PageInfo(width_pts=100.0, height_pts=4500.0)  # at 300 DPI: 4500*300/72 = 18,750 px
    assert should_tile_render(long_banner, dpi=300.0) is True


def test_tiled_render_zero_pixel_drift(tmp_path: Path):
    """1.2 Verify 100% zero-drift pixel equivalence between full page render and tiled render."""
    # Use existing synthetic or fixture PDF (e.g. egihid or comic3 or small synthetic)
    from tests.synthetic_fixtures import make_two_page_spread_pdf
    pdf_path = tmp_path / "sample.pdf"
    make_two_page_spread_pdf(pdf_path)

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    w_pts, h_pts = page.get_size()
    page_info = PageInfo(width_pts=w_pts, height_pts=h_pts)
    dpi = 150.0

    # 1. Reference: direct full-page render
    ref_render = page.render(scale=dpi / 72.0)
    ref_img = ref_render.to_pil().convert("RGB")
    ref_render.close()

    # 2. Candidate: tiled render with small tile_size (100 px) to force multiple tiles
    tiled_path = tmp_path / "tiled_output.png"
    render_page_tiled(
        page=page,
        target_path=tiled_path,
        dpi=dpi,
        page_info=page_info,
        tile_size=100,
        padding=2,
        save_tile_dir=False,
    )

    tiled_img = Image.open(tiled_path).convert("RGB")

    # Dimensions must match exactly
    assert tiled_img.size == ref_img.size

    # Pixel difference must be completely None (0 difference)
    diff = ImageChops.difference(ref_img, tiled_img)
    bbox = diff.getbbox()
    assert bbox is None, f"Detected seam or pixel drift at bbox {bbox}"


def test_tiled_render_with_tile_dir_and_metadata(tmp_path: Path):
    """1.3 Verify tile directory structure and metadata.json generation."""
    from tests.synthetic_fixtures import make_two_page_spread_pdf
    pdf_path = tmp_path / "sample_tiles.pdf"
    make_two_page_spread_pdf(pdf_path)

    doc = pdfium.PdfDocument(str(pdf_path))
    page = doc[0]
    w_pts, h_pts = page.get_size()
    page_info = PageInfo(width_pts=w_pts, height_pts=h_pts)

    tiled_path = tmp_path / "sample_page_01.png"
    produced = render_page_tiled(
        page=page,
        target_path=tiled_path,
        dpi=100.0,
        page_info=page_info,
        tile_size=120,
        padding=2,
        save_tile_dir=True,
    )

    # Must produce target_path
    assert tiled_path.exists()
    assert tiled_path in produced

    # Must produce tile directory and metadata.json
    tile_dir = tmp_path / "sample_page_01_tiles"
    assert tile_dir.exists() and tile_dir.is_dir()
    meta_file = tile_dir / "metadata.json"
    assert meta_file.exists()

    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert "total_width_px" in meta
    assert "tile_size" in meta
    assert "tiles" in meta
    assert len(meta["tiles"]) > 1

    # Check that individual tile files exist on disk
    for t in meta["tiles"]:
        tile_file = tile_dir / t["file"]
        assert tile_file.exists()


def test_render_worker_auto_tile_integration(tmp_path: Path):
    """Verify _render_single_page_to_file automatically delegates to tiled renderer."""
    from tests.synthetic_fixtures import make_two_page_spread_pdf
    from pdf_goon._render_worker import _render_single_page_to_file

    pdf_path = tmp_path / "auto_tile.pdf"
    make_two_page_spread_pdf(pdf_path)

    doc = pdfium.PdfDocument(str(pdf_path))
    out_file = tmp_path / "auto_tile_out.png"

    # Call worker with force_tiles=True to exercise the tiled branch
    _render_single_page_to_file(doc, 1, 150.0, out_file, force_tiles=True)
    assert out_file.exists()
    assert out_file.stat().st_size > 0
    img = Image.open(out_file)
    assert img.size[0] > 0 and img.size[1] > 0
    img.close()
    doc.close()


def test_real_world_io_geological_map_e2e(tmp_path: Path):
    """Verify real-world Io geological map renders under tiled engine with physical evidence."""
    real_pdf = Path("real_test_pdfs/commons_usgs_io_geological_map.pdf")
    if not real_pdf.exists():
        pytest.skip("Real corpus commons_usgs_io_geological_map.pdf not present")

    doc = pdfium.PdfDocument(str(real_pdf))
    page = doc[0]
    w_pts, h_pts = page.get_size()
    page_info = PageInfo(width_pts=w_pts, height_pts=h_pts)

    # Render at 72 DPI (3983 x 2872 px = 11.4 MP) with tile_size=1024 to force 12 tiles
    out_img = tmp_path / "io_map_72dpi.png"
    produced = render_page_tiled(
        page=page,
        target_path=out_img,
        dpi=72.0,
        page_info=page_info,
        tile_size=1024,
        padding=2,
        save_tile_dir=True,
    )
    doc.close()

    assert out_img.exists()
    assert out_img.stat().st_size > 500_000  # physical evidence: substantial PNG bytes
    meta_json = tmp_path / "io_map_72dpi_tiles" / "metadata.json"
    assert meta_json.exists()
    with open(meta_json, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["total_width_px"] == round(w_pts)
    assert meta["total_height_px"] == round(h_pts)
    assert len(meta["tiles"]) == meta["rows"] * meta["cols"]
