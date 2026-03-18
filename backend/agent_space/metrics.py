"""
Prometheus metrics for the jimAI Agent Space.

Metrics exposed:
  jimai_runs_total{status}         - counter, incremented on run completion/failure/stop
  jimai_runs_active                - gauge, current running runs
  jimai_model_request_seconds      - histogram, model inference latency
  jimai_research_requests_total    - counter, research queries
  jimai_run_errors_total           - counter, run errors by type
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        REGISTRY,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.debug("prometheus_client not installed; /metrics endpoint will return fallback response")


if _PROMETHEUS_AVAILABLE:
    # Run lifecycle counters
    RUNS_TOTAL = Counter(
        "jimai_runs_total",
        "Total agent runs by terminal status",
        ["status"],  # completed, failed, stopped
    )
    RUNS_ACTIVE = Gauge(
        "jimai_runs_active",
        "Number of currently active (running) agent runs",
    )
    RUN_ERRORS = Counter(
        "jimai_run_errors_total",
        "Total run errors by error type",
        ["error_type"],  # subagent_error, planner_error, verifier_error, timeout, unknown
    )
    # Model latency
    MODEL_REQUEST_SECONDS = Histogram(
        "jimai_model_request_seconds",
        "Model inference request latency in seconds",
        ["model", "operation"],  # operation: chat, generate, embed
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf")),
    )
    # Research
    RESEARCH_REQUESTS = Counter(
        "jimai_research_requests_total",
        "Total research queries",
        ["provider"],  # searxng, ddg, wikipedia, cache_hit
    )
else:
    # Stub objects so code that calls these doesn't crash when prometheus not installed
    class _Stub:
        def labels(self, **kw): return self
        def inc(self, *a): pass
        def dec(self, *a): pass
        def set(self, *a): pass
        def observe(self, *a): pass
        def time(self): return _StubContext()

    class _StubContext:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    RUNS_TOTAL = _Stub()
    RUNS_ACTIVE = _Stub()
    RUN_ERRORS = _Stub()
    MODEL_REQUEST_SECONDS = _Stub()
    RESEARCH_REQUESTS = _Stub()


# ── Public helpers ────────────────────────────────────────────────────────────

def record_run_started() -> None:
    RUNS_ACTIVE.inc()


def record_run_ended(status: str) -> None:
    """status: completed | failed | stopped"""
    RUNS_ACTIVE.dec()
    RUNS_TOTAL.labels(status=status).inc()


def record_run_error(error_type: str = "unknown") -> None:
    RUN_ERRORS.labels(error_type=error_type).inc()


def record_research_query(provider: str) -> None:
    RESEARCH_REQUESTS.labels(provider=provider).inc()


@contextmanager
def time_model_request(model: str, operation: str = "chat") -> Generator[None, None, None]:
    """Context manager: records model inference latency."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        MODEL_REQUEST_SECONDS.labels(model=model, operation=operation).observe(elapsed)


def get_metrics_output() -> tuple[bytes, str]:
    """Return (body_bytes, content_type) for the /metrics endpoint."""
    if not _PROMETHEUS_AVAILABLE:
        return b"# prometheus_client not installed\n", "text/plain; charset=utf-8"
    return generate_latest(), CONTENT_TYPE_LATEST
