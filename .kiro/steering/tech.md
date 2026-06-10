# Tech Stack

## Language & Runtime

- Python >=3.11
- Uses `from __future__ import annotations` in all modules for PEP 604 style hints

## Build System

- **setuptools** (>=68.0) with `pyproject.toml`
- Entry point: `pdf-goon = pdf_goon.cli:main`

## Dev Dependencies

- **pytest** (>=7.0) — test runner
- **hypothesis** (>=6.0) — property-based testing
- **mypy** (>=1.0) — static type checking
- **ruff** (>=0.1) — linting and formatting

## Common Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy pdf_goon

# Lint
ruff check pdf_goon tests

# Format
ruff format pdf_goon tests

# Build distribution
python -m build
```

## Code Style Conventions

- All modules use frozen dataclasses for data objects
- Functions accept a `run: Callable` parameter for subprocess injection (testability)
- Logging goes to stderr; user-facing output goes to stdout
- Type annotations on all public function signatures
- Module docstrings are single-line summaries of responsibility
- Private helpers prefixed with `_`
- Constants are module-level UPPER_SNAKE_CASE in `models.py`
