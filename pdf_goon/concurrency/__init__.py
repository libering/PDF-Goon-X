"""Concurrency package for pdf_goon: worker pool resolution and execution."""

from __future__ import annotations

from pdf_goon.concurrency.pool import execute_parallel_tasks, resolve_worker_count

__all__ = ["execute_parallel_tasks", "resolve_worker_count"]
