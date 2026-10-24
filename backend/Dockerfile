# DevTrack AI — Backend image (Track 6 ownership).
# Context: ./backend  |  Module layout: app.main:app (WORKDIR /code).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/code

WORKDIR /code

# Runtime C library for psycopg (kept even though psycopg[binary] wheels bundle
# their own libpq, so Track 1 can switch to a non-binary build without a
# Dockerfile change). No curl in this image by design: compose healthchecks
# probe /api/v1/health via stdlib urllib, and the worker healthcheck uses a
# stdlib TCP dial — nothing here needs a shell HTTP client.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      git \
      libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Layer 1: dependencies. If Track 1 later adds backend/requirements.txt,
# it is used as-is; otherwise fall back to the pinned inline set below
# (covers FastAPI + SQLAlchemy 2.0 + psycopg + OTEL + pipeline deps).
COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir \
        "fastapi==0.115.*" \
        "uvicorn[standard]==0.30.*" \
        "pydantic==2.* " \
        "pydantic-settings==2.*" \
        "sqlalchemy==2.*" \
        "psycopg[binary]==3.*" \
        "alembic==1.*" \
        "httpx==0.27.*" \
        "google-genai==1.*" \
        "prometheus-client==0.20.*" \
        "opentelemetry-api==1.*" \
        "opentelemetry-sdk==1.*" \
        "opentelemetry-exporter-otlp==1.*"; \
    fi

# Layer 2: application code (Track 1-3 owned, copied read-only here).
# NOTE: tests/ are deliberately NOT copied into this image — the production
# image must not ship test code (keeps the attack surface + layer size down).
# Track 5 local runs mount them instead:
#   docker compose run --rm -v ./backend/tests:/code/tests:ro backend pytest
COPY app ./app

# Non-root runtime user (least privilege; owns /code for uvicorn + worker).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /code
USER appuser

EXPOSE 8000

# Default = web server. The `worker` service in compose overrides CMD with
# `python -m app.worker.runner` (same image, PostgreSQL-backed job runner).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
