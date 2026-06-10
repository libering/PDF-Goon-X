# tests.test_extract — Tests for pdf_goon.extract

from pathlib import Path

from pdf_goon.extract import extract_images, render_page
from pdf_goon.models import PageInfo


class TestExtractImages:
    """Tests for extract_images command construction and file discovery."""

    def test_builds_correct_pdfimages_command(self, tmp_path: Path) -> None:
        """extract_images passes correct command list to run."""
        captured: list[list[str]] = []

        def recording_run(cmd: list[str]) -> str:
            captured.append(cmd)
            return ""

        pdf_path = tmp_path / "input.pdf"
        output_prefix = tmp_path / "out"

        extract_images(pdf_path, page_num=3, output_prefix=output_prefix, run=recording_run)

        assert len(captured) == 1
        cmd = captured[0]
        assert "pdfimages" in cmd[0]
        assert "-png" in cmd
        assert "-j" in cmd
        assert "-f" in cmd
        assert "-l" in cmd
        f_idx = cmd.index("-f")
        l_idx = cmd.index("-l")
        assert cmd[f_idx + 1] == "3"
        assert cmd[l_idx + 1] == "3"
        assert str(pdf_path) in cmd
        assert str(output_prefix) in cmd

    def test_returns_generated_files(self, tmp_path: Path) -> None:
        """extract_images returns list of files matching the output prefix pattern."""

        def noop_run(cmd: list[str]) -> str:
            return ""

        output_prefix = tmp_path / "page"

        # Create fake output files that pdfimages would generate
        (tmp_path / "page-000.png").touch()
        (tmp_path / "page-001.jpg").touch()
        (tmp_path / "page-002.png").touch()
        # Unrelated file should not be returned
        (tmp_path / "other-000.png").touch()

        pdf_path = tmp_path / "input.pdf"
        result = extract_images(pdf_path, page_num=1, output_prefix=output_prefix, run=noop_run)

        assert len(result) == 3
        names = [p.name for p in result]
        assert "page-000.png" in names
        assert "page-001.jpg" in names
        assert "page-002.png" in names
        assert "other-000.png" not in names


class TestRenderPage:
    """Tests for render_page command construction and surface calculation."""

    def test_builds_correct_pdftocairo_command(self, tmp_path: Path) -> None:
        """render_page passes correct command list to run."""
        captured: list[list[str]] = []

        def recording_run(cmd: list[str]) -> str:
            captured.append(cmd)
            return ""

        pdf_path = tmp_path / "input.pdf"
        output_prefix = tmp_path / "rendered"
        page_info = PageInfo(width_pts=612.0, height_pts=792.0)

        render_page(
            pdf_path,
            page_num=5,
            output_prefix=output_prefix,
            dpi=150.0,
            page_info=page_info,
            run=recording_run,
        )

        assert len(captured) == 1
        cmd = captured[0]
        assert "pdftocairo" in cmd[0]
        assert "-png" in cmd
        assert "-singlefile" in cmd
        assert "-cropbox" in cmd
        assert "-r" in cmd
        r_idx = cmd.index("-r")
        assert cmd[r_idx + 1] == "150.0"
        assert "-W" in cmd
        assert "-H" in cmd
        assert "-f" in cmd
        assert "-l" in cmd
        f_idx = cmd.index("-f")
        l_idx = cmd.index("-l")
        assert cmd[f_idx + 1] == "5"
        assert cmd[l_idx + 1] == "5"
        assert str(pdf_path) in cmd
        assert str(output_prefix) in cmd

    def test_surface_calculation_matches_v1_behavior(self, tmp_path: Path) -> None:
        """render_page computes target_w and target_h matching v1.0.1 GEGL-style calculation."""
        captured: list[list[str]] = []

        def recording_run(cmd: list[str]) -> str:
            captured.append(cmd)
            return ""

        pdf_path = tmp_path / "input.pdf"
        output_prefix = tmp_path / "rendered"
        page_info = PageInfo(width_pts=612.0, height_pts=792.0)
        dpi = 150.0

        render_page(
            pdf_path,
            page_num=1,
            output_prefix=output_prefix,
            dpi=dpi,
            page_info=page_info,
            run=recording_run,
        )

        cmd = captured[0]
        # Expected: int((612.0 * 150) / 72.0) = 1275
        # Expected: int((792.0 * 150) / 72.0) = 1650
        w_idx = cmd.index("-W")
        h_idx = cmd.index("-H")
        assert cmd[w_idx + 1] == "1275"
        assert cmd[h_idx + 1] == "1650"

    def test_returns_generated_files(self, tmp_path: Path) -> None:
        """render_page returns list of files matching the output prefix pattern."""

        def noop_run(cmd: list[str]) -> str:
            return ""

        output_prefix = tmp_path / "rendered"

        # Create fake output file that pdftocairo would generate
        (tmp_path / "rendered.png").touch()

        pdf_path = tmp_path / "input.pdf"
        page_info = PageInfo(width_pts=612.0, height_pts=792.0)

        result = render_page(
            pdf_path,
            page_num=1,
            output_prefix=output_prefix,
            dpi=150.0,
            page_info=page_info,
            run=noop_run,
        )

        assert len(result) == 1
        assert result[0].name == "rendered.png"
