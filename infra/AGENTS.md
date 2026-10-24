# Infrastructure & Observability Agent Rules (`infra/AGENTS.md`)

These rules apply to all agents working inside `infra/`, `.github/workflows/`, and Docker orchestration files.

## 1. Containerization & Resource Budget
- Target host environment: Linux VPS with **4 GB RAM** and **120 GB SSD**.
- Services must be orchestrated via `docker-compose.yml` (development/single-command startup) and `docker-compose.prod.yml` (VPS production with HTTPS Nginx reverse proxy and LGTM observability stack).
- Separate `backend` (FastAPI web server) and `worker` (PostgreSQL-backed background analysis worker) into distinct containers sharing the backend image.
- Enforce sensible memory limits on scanner/worker containers so analysis jobs cannot OOM the 4 GB VPS.

## 2. CI/CD Pipeline Requirements (Maximum 3/3 Rubric Points)
To satisfy the official AI Dev Tools Zoomcamp CI/CD rubric criterion (3/3 points):
1. **CI on Pull Requests:** Automatically run backend `pytest` and frontend build/Playwright checks on every pull request.
2. **Automatic CD to Development/Staging:** Automatically build and deploy on pushes to the development/main staging environment.
3. **Controlled Manual Production Promotion:** Require manual workflow approval (`workflow_dispatch` or protected environment `production` gate) before promoting to production.

## 3. Observability & User-Impact Alerting
- Instrument FastAPI and Worker with **OpenTelemetry** exporting to **Prometheus** (metrics), **Loki** (logs), and **Tempo** (traces), visualized in **Grafana**.
- Never include user email addresses, JWT tokens, or raw API keys in telemetry attributes or log lines.
- Configure actionable alerts in `infra/prometheus/alert_rules.yml` focused on **User Impact** (e.g., high HTTP 5xx rate, p95 response latency > 2s, stuck/failed analysis jobs, or target deployment downtime).

