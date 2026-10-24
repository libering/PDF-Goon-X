"""Deep concurrency module: adaptive worker sizing and robust multiprocessing pool."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import TypeVar

from pdf_goon.models import MAX_DEFAULT_WORKERS

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def resolve_worker_count(jobs_setting: int | None, task_count: int = 1) -> int:
    """Resolve effective worker process count based on setting, CPU count, and tasks.

    - 0 represents auto-detect: min(cpu_count, MAX_DEFAULT_WORKERS, task_count)
    - > 0 represents explicit count: min(jobs, task_count)
    - Always returns an integer >= 1 (defines errors out of existence).
    """
    try:
        setting = int(jobs_setting) if jobs_setting is not None else 1
    except (ValueError, TypeError):
        setting = 1

    bounded_tasks = max(1, task_count)

    if setting <= 0:
        cpu = os.cpu_count() or 1
        effective = min(cpu, MAX_DEFAULT_WORKERS)
        return max(1, min(effective, bounded_tasks))

    return max(1, min(setting, bounded_tasks))


def _execute_sequential(
    tasks: Sequence[T],
    worker_fn: Callable[[T], R],
    progress_callback: Callable[[int, int, R], None] | None = None,
) -> list[R]:
    """Execute tasks sequentially in current process."""
    results: list[R] = []
    total = len(tasks)
    for index, task in enumerate(tasks, 1):
        res = worker_fn(task)
        results.append(res)
        if progress_callback is not None:
            progress_callback(index, total, res)
    return results


def _execute_parallel_pool(
    tasks: Sequence[T],
    worker_fn: Callable[[T], R],
    max_workers: int,
    progress_callback: Callable[[int, int, R], None] | None = None,
) -> list[R]:
    """Execute tasks across ProcessPoolExecutor while maintaining input order."""
    total = len(tasks)
    indexed_results: list[tuple[int, R]] = []
    completed_count = 0

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(worker_fn, task): idx
            for idx, task in enumerate(tasks)
        }
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            res = future.result()
            indexed_results.append((idx, res))
            completed_count += 1
            if progress_callback is not None:
                progress_callback(completed_count, total, res)

    indexed_results.sort(key=lambda item: item[0])
    return [res for _, res in indexed_results]


def execute_parallel_tasks(
    tasks: Sequence[T],
    worker_fn: Callable[[T], R],
    max_workers: int = 1,
    progress_callback: Callable[[int, int, R], None] | None = None,
) -> list[R]:
    """Execute tasks with automatic sequential fallback or process pool mapping."""
    if not tasks:
        return []

    effective_workers = max(1, min(max_workers, len(tasks)))
    if effective_workers <= 1:
        return _execute_sequential(tasks, worker_fn, progress_callback)

    try:
        return _execute_parallel_pool(
            tasks, worker_fn, effective_workers, progress_callback
        )
    except Exception as exc:
        logger.warning(
            "Process pool execution failed (%s); falling back to sequential execution.",
            exc,
        )
        return _execute_sequential(tasks, worker_fn, progress_callback)
