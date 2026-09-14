# tests.test_models — Tests for pdf_goon.models

import dataclasses
import warnings

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pdf_goon.models import (
    DPI_MAX,
    DPI_MIN,
    Config,
    ProcessingMode,
    SubprocessError,
    make_config,
)


# Feature: pdf-goon-refactor, Property 7: Config construction never produces invalid state
@settings(max_examples=100)
@given(dpi_text=st.integers(min_value=-10000, max_value=10000))
def test_config_construction_never_produces_invalid_state(dpi_text: int):
    """make_config either returns a Config with dpi_text in [DPI_MIN, DPI_MAX], or raises ValueError."""
    # Validates: Requirements 7.5, 7.1, 7.2, 7.3
    try:
        config = make_config(path=".", dpi_text=dpi_text)
    except ValueError:
        # ValueError is acceptable — means invalid input was rejected
        pass
    else:
        # If no error, the Config must have dpi_text within valid bounds
        assert isinstance(config, Config)
        assert DPI_MIN <= config.dpi_text <= DPI_MAX, (
            f"Config.dpi_text={config.dpi_text} is outside [{DPI_MIN}, {DPI_MAX}]"
        )
        assert config.path.exists(), "Config.path must point to an existing location"


# --- Unit Tests: Config defaults ---


def test_make_config_defaults():
    """make_config with only path='.' produces correct default values."""
    config = make_config(path=".")
    assert config.verbose is False
    assert config.replace is False
    assert config.optimize is True
    assert config.dpi_text == 400
    assert config.min_width == 500
    assert config.recursive is False
    assert config.force_render is False
    assert config.debug is False


# --- Unit Tests: DPI clamping ---


def test_make_config_dpi_clamped_to_minimum():
    """DPI below minimum is clamped to DPI_MIN (36)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        config = make_config(path=".", dpi_text=10)
    assert config.dpi_text == 36


def test_make_config_dpi_clamped_to_maximum():
    """DPI above maximum is clamped to DPI_MAX (2400)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        config = make_config(path=".", dpi_text=5000)
    assert config.dpi_text == 2400


# --- Unit Tests: debug implies verbose ---


def test_make_config_debug_implies_verbose():
    """Setting debug=True forces verbose=True."""
    config = make_config(path=".", debug=True)
    assert config.verbose is True
    assert config.debug is True


# --- Unit Tests: path validation ---


def test_make_config_nonexistent_path_raises():
    """make_config raises ValueError for a path that does not exist."""
    with pytest.raises(ValueError, match="Path does not exist"):
        make_config(path="/nonexistent/path")


# --- Unit Tests: ProcessingMode enum ---


def test_processing_mode_extract_value():
    """ProcessingMode.EXTRACT has value 'extract'."""
    assert ProcessingMode.EXTRACT.value == "extract"


def test_processing_mode_render_value():
    """ProcessingMode.RENDER has value 'render'."""
    assert ProcessingMode.RENDER.value == "render"


# --- Unit Tests: frozen dataclass immutability ---


def test_config_is_frozen():
    """Assigning to a Config field raises FrozenInstanceError."""
    config = make_config(path=".")
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.verbose = True  # type: ignore[misc]


# --- Unit Tests: exception classes ---


def test_subprocess_error_stores_attributes():
    """SubprocessError stores tool, exit_code, and stderr attributes."""
    err = SubprocessError(tool="pdfinfo", exit_code=1, stderr="file not found")
    assert err.tool == "pdfinfo"
    assert err.exit_code == 1
    assert err.stderr == "file not found"
    assert "pdfinfo" in str(err)
    assert "1" in str(err)
    assert "file not found" in str(err)
