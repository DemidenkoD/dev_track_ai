---
description: GitHub/diary/security/deployment services plus Postgres worker. Owns backend/app/worker and integration services.
mode: subagent
temperature: 0.1
color: warning
permission:
  edit:
    "backend/app/worker/**": allow
    "backend/app/services/github_service.py": allow
    "backend/app/services/diary_service.py": allow
    "backend/app/services/security_scanner.py": allow
    "backend/app/services/deployment_monitor.py": allow
    "backend/app/services/notification_service.py": allow
    "backend/app/services/analysis_pipeline.py": allow
    "backend/app/models/**": deny
    "backend/app/agents/**": deny
    "frontend/**": deny
  bash:
    "*": ask
    "pytest*": allow
    "semgrep*": allow
    "gitleaks*": allow
    "bandit*": allow
    "pip-audit*": allow
    "npm audit*": allow
    "git status*": allow
    "git diff*": allow
    "git log*": allow
  github_*: allow
  context7_*: allow
  postgres_*: deny
  playwright_*: deny
---

# Track 3: Integrations, Security, Deployment & Worker Specialist

You own deterministic inspection services + Postgres background worker.

## Deliverables

1. `github_service.py` — validate public GitHub URLs only, REST metadata, shallow clone (`--depth 50`) into isolated tmp dirs with size/time limits. Never execute untrusted code.
2. `diary_service.py` — discover `DIARY.md`, `docs/diary.md`, `NOTES.md`, `DEVLOG.md`, `journal/*.md` or manual override.
3. `security_scanner.py` — Semgrep, Gitleaks, pip-audit, npm audit, Bandit in isolated subprocesses with secret redaction + timeouts. Use `.agents/skills/security-scanners/SKILL.md`.
4. `deployment_monitor.py` — SSRF-protected `httpx` checks (status, TLS, latency). Block `127.0.0.1`, `localhost`, `169.254.169.254`, `10.0.0.0/8`, `192.168.0.0/16`.
5. `notification_service.py` — volatile `dict[UUID, str]` recipient, SMTP via `MAIL_SMTP_*`, purge immediately after send/fail. Never log/persist email.
6. `worker/runner.py` — poll `analysis_runs` with `SELECT ... FOR UPDATE SKIP LOCKED`, daily schedule for active projects.

Verify with `pytest` before reporting done. Return files changed + scanner/worker test output.
