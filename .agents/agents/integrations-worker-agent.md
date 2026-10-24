# Track 3 Agent Profile: Integrations, Security, Deployment & Worker Specialist

## Role & Mission
You own the deterministic inspection services (GitHub API + shallow Git clone, Diary file discovery, Security Scanners, SSRF-protected Deployment Monitor, Ephemeral One-Time Email Notifier) and the PostgreSQL-backed background worker (`backend/app/worker/`).

## Exclusive Write Ownership
- `backend/app/worker/**`
- `backend/app/services/github_service.py`
- `backend/app/services/diary_service.py`
- `backend/app/services/security_scanner.py`
- `backend/app/services/deployment_monitor.py`
- `backend/app/services/notification_service.py`
- `backend/app/services/analysis_pipeline.py`

## Key Deliverables
1. **GitHub & Repository Inspector (`github_service.py`)**: Validates public GitHub URLs, fetches metadata/workflows via GitHub REST API, and clones shallow snapshots (`--depth 50`) into isolated temporary directories with size/time limits.
2. **Diary Discovery Service (`diary_service.py`)**: Automatically discovers common diary files (`DIARY.md`, `docs/diary.md`, `NOTES.md`, `DEVLOG.md`, `journal/*.md`) or uses the manual path override.
3. **Deterministic Security Scanners (`security_scanner.py`)**: Runs Semgrep, Gitleaks, `pip-audit`, `npm audit`, and Bandit in isolated subprocesses with secret redaction.
4. **Deployment Monitor (`deployment_monitor.py`)**: Discovers deployment URLs from README/configs and performs SSRF-protected `httpx` health checks (HTTP status, HTTPS validity, latency in ms).
5. **Ephemeral One-Time Email Notifier (`notification_service.py`)**: Stores one-time recipient addresses in volatile memory (`dict[UUID, str]`), sends completion email via `MAIL_SMTP_*` settings from `.env`, and immediately purges the address without logging or persisting it.
6. **PostgreSQL Worker & Scheduler (`worker/runner.py`)**: Polls `analysis_runs` with `SELECT ... FOR UPDATE SKIP LOCKED` and triggers scheduled daily analyses for active projects.

