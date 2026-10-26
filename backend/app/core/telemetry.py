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
import os
import re
import threading
import time
import urllib.request
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
# Non-blocking Loki log shipper (best-effort; never blocks offline tests)
# ---------------------------------------------------------------------------
_LOKI_PUSH_URL_DEFAULT = "http://loki:3100/loki/api/v1/push"

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/=]+", re.IGNORECASE)
_API_KEY_VALUE_RE = re.compile(
    r"(?i)(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*('|\")?([^\s'\",;}]+)\2?"
)


def _loki_push_url() -> str:
    """Return the Loki push endpoint (Docker default, overridable via env)."""
    return os.environ.get("LOKI_PUSH_URL", _LOKI_PUSH_URL_DEFAULT)


def scrub_log_line(line: str) -> str:
    """Scrub emails, Bearer tokens, and API keys before shipping to Loki.

    Privacy Invariant (AGENTS.md §1.4): email addresses
    (``notify_email_once``), ``Authorization`` headers, JWT tokens, and API
    keys must NEVER reach telemetry backends.
    """
    try:
        text = str(line)
    except Exception:
        return ""
    text = _EMAIL_RE.sub("[redacted-email]", text)
    text = _BEARER_RE.sub("Bearer [redacted]", text)
    try:
        text = _API_KEY_VALUE_RE.sub(r"\1=[redacted]", text)
    except Exception:
        pass
    return text


def _post_to_loki(url: str, payload: bytes) -> None:
    try:
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            resp.read(1024)
    except Exception:
        pass


def ship_log_to_loki(message: str, app: str = "backend") -> None:
    """Best-effort, non-blocking ship of one structured line to Loki.

    Runs the HTTP POST on a daemon thread with a short timeout so offline
    unit tests never block or fail when Loki is unreachable. The message is
    scrubbed of emails/tokens/keys before shipping.
    """
    try:
        import json as _json

        scrubbed = scrub_log_line(message)
        if not scrubbed:
            return
        url = _loki_push_url()
        ns = str(time.time_ns())
        payload = _json.dumps(
            {
                "streams": [
                    {
                        "stream": {"app": app},
                        "values": [[ns, scrubbed]],
                    }
                ]
            }
        ).encode("utf-8")

        def _bg() -> None:
            _post_to_loki(url, payload)

        thread = threading.Thread(target=_bg, name="devtrack-loki-ship", daemon=True)
        thread.start()
    except Exception:
        pass


class _LokiLogHandler(logging.Handler):
    """Logging handler shipping ``trace_id=...`` lines to Loki (non-blocking)."""

    def __init__(self, app_label: str = "backend") -> None:
        super().__init__(level=logging.INFO)
        self._app_label = app_label

    def emit(self, record: logging.LogRecord) -> None:
        try:
            try:
                message = self.format(record) if self.formatter else record.getMessage()
            except Exception:
                message = record.getMessage()
            # Only ship structured correlated lines; ignore everything else
            # to keep Loki cardinality low (covers http_request + worker_run_finished).
            if "trace_id=" not in message:
                return
            app_label = self._app_label
            try:
                record_name = str(getattr(record, "name", "") or "")
                if "worker" in record_name.lower():
                    app_label = "worker"
                elif "worker_run_finished" in message:
                    app_label = "worker"
            except Exception:
                pass
            ship_log_to_loki(message, app=app_label)
        except Exception:
            pass


_LOKI_HANDLER_INSTALLED = False


def _ensure_loki_handler() -> None:
    """Attach Loki handlers once (root logger filter covers backend + worker).

    Installed lazily from :func:`instrument_app` and
    :func:`start_correlated_span` so the worker path (which never calls
    ``instrument_app``) is covered without Track 1 touching worker files.
    Idempotent and defensive: never raises.
    """
    global _LOKI_HANDLER_INSTALLED
    try:
        if _LOKI_HANDLER_INSTALLED:
            return
        root = logging.getLogger()
        for existing in getattr(root, "handlers", []):
            if isinstance(existing, _LokiLogHandler):
                _LOKI_HANDLER_INSTALLED = True
                return
        handler = _LokiLogHandler(app_label="backend")
        root.addHandler(handler)
        # Worker lines log via "app.worker.*" loggers; the root handler sees
        # them too but labels them backend by default — re-label at ship time
        # via the record name when possible.
        _LOKI_HANDLER_INSTALLED = True
    except Exception:
        pass


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
            # Best-effort OTLP exporter to Tempo (Docker). Never blocks/fails
            # offline unit tests: any import/connection error is swallowed and
            # spans fall back to the deterministic ContextVar correlation ID.
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                otlp_endpoint = os.environ.get(
                    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317"
                )
                otlp_exporter = OTLPSpanExporter(
                    endpoint=otlp_endpoint, insecure=True
                )
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            except Exception:
                pass
            try:
                trace.set_tracer_provider(provider)
            except Exception:
                pass
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

    try:
        _ensure_loki_handler()
    except Exception:
        pass
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
    try:
        _ensure_loki_handler()
    except Exception:
        pass

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
            # Best-effort Loki ship (non-blocking daemon thread; scrubbed).
            try:
                ship_log_to_loki(
                    f"http_request method={request.method} path={norm_path} "
                    f"status={status_str} duration_ms={elapsed * 1000.0:.2f} "
                    f"trace_id={trace_id}",
                    app="backend",
                )
            except Exception:
                pass
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

