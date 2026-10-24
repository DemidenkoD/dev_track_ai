"""Security Reviewer runtime agent (Track 2).

Explains deterministic scanner JSON (Semgrep, Gitleaks, pip-audit, npm audit,
Bandit) in developer-friendly language, deduplicates noise, assesses
exploitability in a course-project context, and ranks remediation.

Secret-redaction rule (from ``backend/app/agents/AGENTS.md``): raw secret
values from Gitleaks / ``.env`` files must NEVER be sent to Gemini. Only
rule IDs, file paths, line numbers, and redacted snippets cross the boundary
— enforced by :func:`redact_findings` before prompt construction.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

try:
    from app.agents.base import ADVISORY_NOTICE, run_with_fallback
except ImportError:  # harness imports as backend.app.*: fix sys.path first
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from app.agents.base import ADVISORY_NOTICE, run_with_fallback

from app.schemas.agent_outputs import ExplainedSecurityFinding, SecurityReviewOutput
from app.schemas.enums import SecurityStatus, SeverityLevel

SECURITY_SYSTEM = (
    "You are DevTrack AI's Security Reviewer. Given redacted deterministic "
    "scanner findings (semgrep, gitleaks, pip-audit, npm-audit, bandit), "
    "explain each in plain developer-friendly language, deduplicate scanner "
    "noise, assess exploitability specifically for a student course project, "
    "and rank remediation by priority_rank (1 = fix first). Set overall_status "
    "to 'critical' if any critical exploitable issue exists, 'warning' if "
    "non-trivial issues exist, else 'pass'. Findings contain NO raw secrets — "
    "only rule IDs, paths, lines, and redacted snippets."
)

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"]?([^\s'\";]+)['\"]?"),
    re.compile(r"sk-(?:live|test)-[A-Za-z0-9]+"),
    re.compile(r"ghp_[A-Za-z0-9]+"),
    re.compile(r"xox[bap]-?[A-Za-z0-9-]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]

_SCANNER_SEVERITY_RANK = {
    "critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5,
}


def redact_text(text: str | None) -> str:
    """Replace probable secret values with ``[REDACTED]`` (defence in depth)."""
    if not text:
        return ""
    redacted = text
    for pat in _SECRET_PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    # Generic long high-entropy token heuristic.
    redacted = re.sub(r"['\"][A-Za-z0-9_\-+/=]{24,}['\"]", "[REDACTED]", redacted)
    return redacted[:2000]


def redact_findings(raw_findings: Sequence[Any]) -> list[dict[str, Any]]:
    """Strip raw secrets; keep only scanner/rule/path/line/redacted snippet."""
    out: list[dict[str, Any]] = []
    for f in raw_findings:
        if isinstance(f, dict):
            out.append(
                {
                    "scanner": str(f.get("scanner", "unknown")),
                    "rule_id": str(f.get("rule_id", f.get("rule", "unknown"))),
                    "severity": str(f.get("severity", "info")).lower(),
                    "file_path": f.get("file_path"),
                    "line_number": f.get("line_number"),
                    "message": redact_text(
                        str(f.get("raw_message", f.get("message", f.get("title", ""))))
                    ),
                }
            )
        else:
            out.append(
                {
                    "scanner": str(getattr(f, "scanner", "unknown")),
                    "rule_id": str(getattr(f, "rule_id", "unknown")),
                    "severity": str(getattr(f, "severity", "info")).lower(),
                    "file_path": getattr(f, "file_path", None),
                    "line_number": getattr(f, "line_number", None),
                    "message": redact_text(
                        str(getattr(f, "raw_message", getattr(f, "message", "")))
                    ),
                }
            )
    return out


def _dedupe(redacted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for f in redacted:
        key = (f["scanner"], f["rule_id"], str(f.get("file_path") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    unique.sort(
        key=lambda f: (
            _SCANNER_SEVERITY_RANK.get(f.get("severity", "info"), 5),
            f.get("scanner", ""),
            f.get("rule_id", ""),
        )
    )
    return unique


def _severity_of(value: str) -> SeverityLevel:
    try:
        return SeverityLevel(value.lower())
    except ValueError:
        return SeverityLevel.INFO


def fallback_security_review(
    raw_findings: Sequence[Any] | None = None,
    scanners_executed: Sequence[str] | None = None,
    error: Exception | None = None,  # noqa: ARG001
) -> SecurityReviewOutput:
    """Deterministic prioritization without LLM (offline/CI safe)."""
    redacted = _dedupe(redact_findings(list(raw_findings or [])))
    explained: list[ExplainedSecurityFinding] = []
    worst = "pass"
    for rank, f in enumerate(redacted, start=1):
        sev = _severity_of(f.get("severity", "info"))
        if sev == SeverityLevel.CRITICAL:
            worst = "critical"
        elif sev in (SeverityLevel.HIGH, SeverityLevel.MEDIUM) and worst != "critical":
            worst = "warning"
        explained.append(
            ExplainedSecurityFinding(
                scanner=f["scanner"],
                rule_id=f["rule_id"],
                severity=sev,
                file_path=f.get("file_path"),
                line_number=f.get("line_number"),
                ai_explanation=(
                    f"Offline fallback explanation for {f['scanner']}:{f['rule_id']} "
                    f"at {f.get('file_path') or 'unknown location'}: "
                    f"{f.get('message', '')[:300]} Reviewer should triage manually."
                ),
                ai_remediation=(
                    "Offline fallback: rotate any exposed credential, restrict file "
                    "permissions, add the path to .gitignore / secret scanning, and "
                    "re-run the deterministic scanner."
                ),
                priority_rank=rank,
            )
        )
    status = {
        "pass": SecurityStatus.PASS,
        "warning": SecurityStatus.WARNING,
        "critical": SecurityStatus.CRITICAL,
    }[worst]
    scanners = list(scanners_executed or ["semgrep", "gitleaks", "pip-audit", "npm-audit", "bandit"])
    return SecurityReviewOutput(
        overall_status=status,
        ai_executive_summary=(
            f"Deterministic offline security triage over {len(explained)} unique "
            f"finding(s) from {', '.join(scanners)}. Gemini unavailable — "
            f"all items need human review. " + ADVISORY_NOTICE
        ),
        prioritized_findings=explained,
    )


def review_findings(
    raw_findings: Sequence[Any] | None = None,
    scanners_executed: Sequence[str] | None = None,
    commit_sha: str | None = None,
) -> SecurityReviewOutput:
    """Explain + prioritize scanner output (secrets redacted before prompting)."""
    redacted = _dedupe(redact_findings(list(raw_findings or [])))

    def _prompt() -> tuple[str, str]:
        if not redacted:
            body = "(no findings reported by deterministic scanners)"
        else:
            lines = [
                f"- [{f['scanner']}:{f['rule_id']}] severity={f['severity']} "
                f"file={f.get('file_path') or '?'} line={f.get('line_number') or '?'} :: "
                f"{f.get('message', '')[:400]}"
                for f in redacted[:60]
            ]
            body = "\n".join(lines)
        user = (
            f"commit_sha={commit_sha or 'unknown'}\n"
            f"Scanners executed: {', '.join(scanners_executed or []) or 'unknown'}\n\n"
            f"REDACTED FINDINGS (no raw secrets included):\n{body}\n\n"
            "Return overall_status, ai_executive_summary, and prioritized_findings "
            "with ai_explanation, ai_remediation, and priority_rank per finding."
        )
        return (SECURITY_SYSTEM, user)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=SecurityReviewOutput,
        parse=lambda raw: SecurityReviewOutput.model_validate(raw),
        fallback=lambda exc: fallback_security_review(raw_findings, scanners_executed, exc),
    )
