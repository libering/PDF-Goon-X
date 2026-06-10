# Project Structure

```
pdf_goon/
├── __init__.py    # Public API: process() function, re-exports
├── models.py      # Dataclasses, enums, constants, exceptions, Config factory
├── cli.py         # Thin CLI layer: argparse → Config → process() → exit code
├── core.py        # Orchestration: batch processing, single-PDF pipeline, progress
├── analyze.py     # PDF inspection: page count, image metadata, page dimensions, mode decisions
├── extract.py     # Image extraction (pdfimages) and page rendering (pdftocairo)
├── files.py       # File operations: unique paths, trash/move, temp workspace context manager
├── optimize.py    # Lossless image optimization (pingo/oxipng/jpegoptim)
├── tools.py       # Tool path resolution, subprocess execution, Poppler availability checks
tests/
├── test_analyze.py
├── test_cli.py
├── test_core.py
├── test_extract.py
├── test_files.py
├── test_init.py
├── test_integration.py
├── test_models.py
├── test_optimize.py
├── test_tools.py
```

## Architecture Layers

1. **CLI** (`cli.py`) — Parses args, prints banner, delegates to public API
2. **Public API** (`__init__.py`) — `process()` constructs Config and calls `process_batch`
3. **Orchestration** (`core.py`) — Iterates PDFs, per-page pipeline, progress reporting
4. **Analysis** (`analyze.py`) — Inspects PDFs via Poppler, decides extract vs render
5. **Execution** (`extract.py`, `optimize.py`) — Runs Poppler/optimizer subprocesses
6. **Infrastructure** (`files.py`, `tools.py`, `models.py`) — Shared utilities, data types, tool resolution

## Key Design Patterns

- **Dependency injection for subprocesses**: Functions accept `run: Callable[[list[str]], str]` so tests can substitute fakes without mocking
- **Immutable configuration**: `Config` is a frozen dataclass constructed via `make_config()` factory with validation
- **Context-managed workspaces**: Temp directories for intermediate files are cleaned up via `workspace_context()`
- **Structured results**: Processing outcomes returned as `ProcessResult` dataclasses, not print statements
- **Layered error handling**: Custom exception hierarchy (`PdfGoonError` → `ToolNotFoundError`, `SubprocessError`)
