"""OpenTelemetry & Prometheus observability instrumentation (Issue #6, #7, #8).

Guarantees:
1. Exposes `GET /metrics` for Prometheus scraping (`http_requests_total`,
   `http_request_duration_seconds`, `analysis_runs_failed_total`).
2. Creates an OpenTelemetry span per HTTP request and per analysis run so
   metrics, structured logs (`trace_id=...`), and traces share the same
   correlation `trace_id`.
3. Privacy Invariant (AGENTS.md §1.4 & infra/AGENTS.md §3): NEVER attaches
   email addresses (`notify_email_once`), `Authorization` headers, JWT tokens,
   or API keys to span attributes, metrics labels, or log records.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("devtrack.telemetry")

_current_trace_id: ContextVar[str] = ContextVar("devtrack_trace_id", default="")

# ---------------------------------------------------------------------------
# Prometheus metrics (with lightweight fallback if prometheus_client absent)
# ---------------------------------------------------------------------------
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
         REGISTRY,
        Counter,
        Histogram,
        generate_latest,
    )

    def _get_or_create_counter(name: str, doc: str, labelnames: tuple[str, ...] = ()):
        if name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[name]
        return Counter(name, doc, labelnames)

    def _get_or_create_histogram(name: str, doc: str, labelnames: tuple[str, ...] = ()):
        if name in REGISTRY._names_to_collectors:
            return REGISTRY._names_to_collectors[name]
        return Histogram(name, doc, labelnames)

    HTTP_REQUESTS_TOTAL = _get_or_create_counter(
        "http_requests_total",
        "Total HTTP requests by method, normalized path, and status code.",
        ("method", "path", "status"),
    )
    HTTP_REQUEST_DURATION_SECONDS = _get_or_create_histogram(
        "http_request_duration_seconds",
        "HTTP request latency distribution in seconds.",
        ("method", "path"),
    )
    ANALYSIS_RUNS_FAILED_TOTAL = _get_or_create_counter(
        "analysis_runs_failed_total",
        "Total number of analysis runs that ended in failed status.",
    )
    ANALYSIS_RUNS_COMPLETED_TOTAL = _get_or_create_counter(
        "analysis_runs_completed_total",
        "Total number of analysis runs that completed successfully.",
    )
    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover - fallback when prometheus_client not installed
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    _PROM_AVAILABLE = False
    _FALLBACK_COUNTERS: dict[str, int] = {
        "http_requests_total": 0,
        "analysis_runs_failed_total": 0,
        "analysis_runs_completed_total": 0,
    }


def record_analysis_run_outcome(success: bool) -> None:
    """Increment Prometheus counters for worker/API analysis job outcomes."""
    if _PROM_AVAILABLE:
        if success:
            ANALYSIS_RUNS_COMPLETED_TOTAL.inc()
        else:
            ANALYSIS_RUNS_FAILED_TOTAL.inc()
    else:
        key = "analysis_runs_completed_total" if success else "analysis_runs_failed_total"
        _FALLBACK_COUNTERS[key] = _FALLBACK_COUNTERS.get(key, 0) + 1


# ---------------------------------------------------------------------------
# OpenTelemetry Tracer (with deterministic correlation trace_id fallback)
# ---------------------------------------------------------------------------
_OTEL_INITIALIZED = False


def _ensure_otel_tracer(service_name: str = "devtrack-ai-backend"):
    global _OTEL_INITIALIZED
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        if not _OTEL_INITIALIZED:
            provider = TracerProvider(
                resource=Resource.create({"service.name": service_name})
            )
            trace.set_tracer_provider(provider)
            _OTEL_INITIALIZED = True
        return trace.get_tracer(service_name)
    except Exception:
        return None


def get_current_trace_id() -> str:
    """Return active 32-hex OpenTelemetry trace_id or ContextVar correlation ID."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is not None:
            ctx = span.get_span_context()
            if ctx is not None and getattr(ctx, "is_valid", False):
                return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return _current_trace_id.get() or uuid.uuid4().hex


@contextmanager
def start_correlated_span(
    name: str, attributes: dict[str, Any] | None = None
) -> Iterator[str]:
    """Start an OpenTelemetry span and yield its 32-char hex `trace_id`.

    Scrubs any key containing 'email', 'token', 'password', 'secret', or 'key'
    so sensitive values never enter telemetry spans.
    """
    safe_attrs: dict[str, Any] = {}
    for k, v in (attributes or {}).items():
        lowered = k.lower()
        if any(
            bad in lowered
            for bad in ("email", "token", "password", "secret", "key", "auth")
        ):
            continue
        safe_attrs[k] = str(v)

    tracer = _ensure_otel_tracer()
    if tracer is not None:
        with tracer.start_as_current_span(name) as span:
            for k, v in safe_attrs.items():
                try:
                    span.set_attribute(k, v)
                except Exception:
                    pass
            trace_id = get_current_trace_id()
            token = _current_trace_id.set(trace_id)
            try:
                yield trace_id
            finally:
                _current_trace_id.reset(token)
    else:
        trace_id = _current_trace_id.get() or uuid.uuid4().hex
        token = _current_trace_id.set(trace_id)
        try:
            yield trace_id
        finally:
            _current_trace_id.reset(token)


def _normalize_path(path: str) -> str:
    """Collapse UUID segments to `{id}` to prevent metric label cardinality explosion."""
    parts = []
    for segment in path.split("/"):
        if len(segment) == 36 and segment.count("-") == 4:
            parts.append("{id}")
        else:
            parts.append(segment)
    return "/".join(parts) or "/"


def instrument_app(app: FastAPI) -> None:
    """Attach trace-correlated HTTP middleware and `GET /metrics` to FastAPI."""

    @app.middleware("http")
    async def _telemetry_middleware(request: Request, call_next: Callable):
        norm_path = _normalize_path(request.url.path)
        start = time.perf_counter()
        with start_correlated_span(
            f"{request.method} {norm_path}",
            attributes={
                "http.method": request.method,
                "http.route": norm_path,
            },
        ) as trace_id:
            response: Response = await call_next(request)
            elapsed = max(0.0, time.perf_counter() - start)
            status_str = str(response.status_code)
            if _PROM_AVAILABLE:
                HTTP_REQUESTS_TOTAL.labels(
                    method=request.method, path=norm_path, status=status_str
                ).inc()
                HTTP_REQUEST_DURATION_SECONDS.labels(
                    method=request.method, path=norm_path
                ).observe(elapsed)
            else:
                _FALLBACK_COUNTERS["http_requests_total"] += 1

            response.headers["X-Trace-Id"] = trace_id
            # Structured log line correlating metrics + logs + traces via trace_id
            # (never logs request body, query params, or headers).
            logger.info(
                "http_request method=%s path=%s status=%s duration_ms=%.2f trace_id=%s",
                request.method,
                norm_path,
                status_str,
                elapsed * 1000.0,
                trace_id,
            )
            return response

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        if _PROM_AVAILABLE:
            return Response(
                content=generate_latest(REGISTRY),
                media_type=CONTENT_TYPE_LATEST,
            )
        lines = [
            f"# HELP {k} Fallback counter\n# TYPE {k} counter\n{k} {v}"
            for k, v in _FALLBACK_COUNTERS.items()
        ]
        return Response(
            content="\n".join(lines) + "\n",
            media_type=CONTENT_TYPE_LATEST,
        )
