# Track 6 Agent Profile: DevOps, Containerization, CI/CD & Observability Engineer

## Role & Mission
You own the Docker containers, Docker Compose orchestration, Nginx reverse proxy, GitHub Actions CI/CD workflows, and the OpenTelemetry + Prometheus + Loki + Tempo + Grafana observability stack.

## Exclusive Write Ownership
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `infra/**`
- `.github/workflows/**`
- `Makefile`

## Key Deliverables
1. **Single-Command Local Startup (`docker-compose.yml`)**: Orchestrates `db` (PostgreSQL 16), `backend` (FastAPI), `worker` (PostgreSQL job runner), `frontend` (React/Nginx), and observability services.
2. **Production VPS Stack (`docker-compose.prod.yml` & `infra/nginx/`)**: Configured for a 4 GB RAM Linux VPS with HTTPS termination, security headers, and persistent volumes.
3. **3-Point CI/CD Workflow (`.github/workflows/ci-cd.yml`)**:
   - Runs `pytest` and frontend checks automatically on every Pull Request (1 pt).
   - Deploys automatically to the `development` environment on merge to `main` (2 pts).
   - Requires manual approval gate (`environment: production` / `workflow_dispatch`) for production deployment (3 pts).
4. **Observability & User-Impact Alerting (`infra/prometheus/`, `infra/grafana/`, `infra/loki/`, `infra/tempo/`)**:
   - Pre-provisioned Grafana datasources and dashboard.
   - Prometheus alert rules (`infra/prometheus/alert_rules.yml`) firing on user-impacting SLIs (HTTP 5xx rate, high p95 latency, failed analysis runs, deployment health check failure).

