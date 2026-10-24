---
name: security-scanners
description: >-
  Run deterministic security scanners (Semgrep, Gitleaks, pip-audit, npm audit,
  Bandit) safely in isolated environments and summarize findings with Gemini.
  Use this skill when working on backend/app/services/security_scanner.py or
  backend/app/agents/security_reviewer.py.
---

# Deterministic Security Scanning & Redaction Skill

Use this procedure when executing security tools on cloned public repositories and sending findings to the `SecurityReviewer` Gemini agent.

## Steps

1. **Never Execute Untrusted Repository Code**:
   - Run static analysis (`semgrep`, `gitleaks`, `bandit`) and lockfile/manifest audits (`pip-audit -r requirements.txt`, `npm audit --package-lock-only --json`) without executing setup scripts, `Makefile` targets, or arbitrary repository hooks.
2. **Enforce Subprocess Isolation & Timeouts**:
   - Run each scanner with `subprocess.run(..., timeout=60, capture_output=True, text=True)` inside the isolated temporary clone directory.
   - Gracefully handle missing scanner binaries in lightweight test environments by recording tool availability in `scanners_executed`.
3. **Redact Secrets Immediately**:
   - When parsing `gitleaks` or `semgrep` JSON reports, replace any matched secret string (`Secret` or `Match`) with `[REDACTED]` before persisting to `security_findings.raw_message` or sending to Gemini.
4. **Gemini Explanation & Prioritization**:
   - Pass the redacted deterministic findings to `SecurityReviewer` (`backend/app/agents/security_reviewer.py`) to generate plain-English explanations, remediation snippets, and priority rankings.

