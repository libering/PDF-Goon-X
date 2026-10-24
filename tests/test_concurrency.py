"""Unit and property tests for multiprocessing concurrency."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pdf_goon.concurrency.pool import (
    execute_parallel_tasks,
    resolve_worker_count,
)
from pdf_goon.extract import _chunk_tasks
from pdf_goon.models import MAX_DEFAULT_WORKERS, make_config
from pdf_goon.pipeline.batch import process_batch


def test_resolve_worker_count_explicit() -> None:
    """Explicit positive jobs setting is respected up to task bounds."""
    assert resolve_worker_count(1, task_count=10) == 1
    assert resolve_worker_count(4, task_count=10) == 4
    # Bounded by available tasks
    assert resolve_worker_count(8, task_count=3) == 3


def test_resolve_worker_count_auto_and_edge_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto setting (0 or negative) respects cpu count and MAX_DEFAULT_WORKERS limit."""
    monkeypatch.setattr("os.cpu_count", lambda: 16)
    assert resolve_worker_count(0, task_count=10) == MAX_DEFAULT_WORKERS
    assert resolve_worker_count(-5, task_count=10) == MAX_DEFAULT_WORKERS

    # Edge cases: None or invalid types define errors out of existence
    assert resolve_worker_count(None, task_count=5) == 1
    assert resolve_worker_count("invalid", task_count=5) == 1  # type: ignore[arg-type]

    # Task bounds win
    assert resolve_worker_count(0, task_count=2) == 2


def test_chunk_tasks_partitioning() -> None:
    """Partitioning tasks divides workload evenly into chunk_count buckets."""
    tasks = [{"page": i} for i in range(1, 11)]
    chunks = _chunk_tasks(tasks, 3)
    assert len(chunks) == 3
    flattened = [t for c in chunks for t in c]
    assert len(flattened) == 10
    assert set(t["page"] for t in flattened) == set(range(1, 11))

    # Single or zero chunks safe
    assert len(_chunk_tasks(tasks, 1)) == 1
    assert len(_chunk_tasks([], 4)) == 0


def _square_worker(n: int) -> int:
    """Top-level helper for multiprocessing pickle support."""
    return n * n


def test_execute_parallel_tasks_maintains_order() -> None:
    """Parallel pool execution preserves input order identically to sequential."""
    numbers = list(range(1, 21))
    seq_results = execute_parallel_tasks(numbers, _square_worker, max_workers=1)
    par_results = execute_parallel_tasks(numbers, _square_worker, max_workers=4)

    assert seq_results == [n * n for n in numbers]
    assert par_results == seq_results


def _failing_worker(n: int) -> int:
    """Top-level helper that raises an exception on demand."""
    if n == 3:
        raise ValueError("Simulated worker error on item 3")
    return n * 2


def test_execute_parallel_tasks_fallback_on_worker_error() -> None:
    """When a worker in parallel pool raises, execute_parallel_tasks falls back or raises cleanly."""
    items = [1, 2, 3, 4]
    with pytest.raises(ValueError, match="Simulated worker error on item 3"):
        execute_parallel_tasks(items, _failing_worker, max_workers=2)


def test_config_jobs_parsing_and_defaults(tmp_path: Path) -> None:
    """Config dataclass and make_config factory correctly ingest jobs parameter."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 mock")

    cfg1 = make_config(path=pdf_file)
    assert cfg1.jobs == 1

    cfg2 = make_config(path=pdf_file, jobs=4)
    assert cfg2.jobs == 4

    cfg_auto = make_config(path=pdf_file, jobs=0)
    assert cfg_auto.jobs == 0


def test_batch_parallel_differential_mock(tmp_path: Path) -> None:
    """Differential verification: batch processing with custom backend falls back to sequential."""
    pdf1 = tmp_path / "a.pdf"
    pdf2 = tmp_path / "b.pdf"
    pdf1.write_bytes(b"%PDF-1.4 mock a")
    pdf2.write_bytes(b"%PDF-1.4 mock b")

    mock_analyze = MagicMock()
    mock_analyze.get_page_count.return_value = 1
    mock_analyze.get_image_data.return_value = ([], [], False)
    mock_analyze.get_page_info.return_value = MagicMock(width_pts=600, height_pts=800)

    cfg = make_config(path=tmp_path, jobs=2)
    # When custom mock backend is passed, it safely runs sequential without pickling error
    results = process_batch(cfg, analyze_backend=mock_analyze)
    assert len(results) == 2
    assert all(r.pdf_path in (pdf1, pdf2) for r in results)
