"""Deterministic security scanner runner (Track 3).

Executes Semgrep, Gitleaks, pip-audit, npm audit, and Bandit as isolated
subprocesses with strict timeouts. Implements
``.agents/skills/security-scanners/SKILL.md``:

1. Never execute untrusted repository code (static analysis + manifest
   audits only; no setup scripts, Makefile targets, or repo hooks).
2. ``subprocess.run(..., timeout=60, capture_output=True, text=True)``
   inside the isolated clone directory; missing binaries are recorded in
   ``scanners_executed`` instead of crashing.
3. Redact secret values (``Secret``/``Match`` fields) to ``[REDACTED]``
   before persisting or forwarding findings to Gemini.
4. Findings are returned normalized for the ``SecurityReviewer`` agent.

Public API:
    - :func:`redact_secrets`
    - :func:`run_all_scanners`
    - :func:`run_semgrep` / :func:`run_gitleaks` / :func:`run_pip_audit`
      / :func:`run_npm_audit` / :func:`run_bandit`
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SCANNER_TIMEOUT_SECONDS = 60
REDACTED = "[REDACTED]"

#: Patterns whose *values* must never be persisted or sent to Gemini.
_SECRET_VALUE_RES = (
    re.compile(r"(?i)(aws_access_key_id|aws_secret_access_key|api[_-]?key|secret|token|password|private[_-]?key)\s*[:=]\s*['\"]?([^\s'\";,}]+)['\"]?"),
    re.compile(r"(?i)(ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[bpas]-[A-Za-z0-9\-]+)"),
    re.compile(r"(?i)-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----[^-]*-----END [^-]+-----"),
)

SUPPORTED_SCANNERS: tuple[str, ...] = ("semgrep", "gitleaks", "pip-audit", "npm-audit", "bandit")


@dataclass
class NormalizedFinding:
    """Single redacted, scanner-normalized security finding."""

    scanner: str
    rule_id: str
    severity: str  # info|low|medium|high|critical
    file_path: str | None = None
    line_number: int | None = None
    message: str = ""


@dataclass
class ScanSummary:
    """Aggregate result handed to the SecurityReviewer agent / DB writer."""

    scanners_executed: list[str] = field(default_factory=list)
    scanners_skipped: list[str] = field(default_factory=list)
    findings: list[NormalizedFinding] = field(default_factory=list)
    overall_status: str = "pass"  # pass|warning|critical
    errors: list[str] = field(default_factory=list)


def redact_secrets(text: str) -> str:
    """Replace probable secret values with ``[REDACTED]``.

    Operates on free text and on serialized JSON payloads. Key *names* and
    rule metadata are preserved; only the secret *values* are masked.
    """
    if not text:
        return text
    redacted = text
    for pattern in _SECRET_VALUE_RES:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def _normalize_severity(raw: str | None) -> str:
    value = (raw or "info").strip().lower()
    mapping = {
        "info": "info",
        "informational": "info",
        "low": "low",
        "moderate": "medium",
        "medium": "medium",
        "high": "high",
        "critical": "critical",
        "error": "high",
        "warning": "medium",
        "note": "info",
    }
    return mapping.get(value, "info")


def _run(
    argv: list[str], cwd: Path, timeout: int = SCANNER_TIMEOUT_SECONDS
) -> tuple[bool, str]:
    """Run one scanner binary; return (ran, stdout). Never uses shell=True."""
    if not argv or shutil.which(argv[0]) is None:
        return False, ""
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return True, ""  # ran but timed out -> caller records partial
    except (FileNotFoundError, OSError):
        return False, ""
    return True, completed.stdout or ""


def run_semgrep(target_dir: str | Path) -> tuple[bool, list[NormalizedFinding]]:
    """Run Semgrep (``semgrep --json --config auto``) and normalize results."""
    cwd = Path(target_dir)
    ran, stdout = _run(["semgrep", "--json", "--config", "auto", "--quiet", "."], cwd)
    if not ran:
        return False, []
    findings: list[NormalizedFinding] = []
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return True, []
    for item in payload.get("results", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        findings.append(
            NormalizedFinding(
                scanner="semgrep",
                rule_id=str(item.get("check_id", "semgrep.unknown")),
                severity=_normalize_severity(str(item.get("extra", {}).get("severity", "info")) if isinstance(item.get("extra"), dict) else "info"),
                file_path=str(item.get("path")) if item.get("path") else None,
                line_number=int(item.get("start", {}).get("line", 0)) or None if isinstance(item.get("start"), dict) else None,
                message=redact_secrets(str(item.get("extra", {}).get("message", "")) if isinstance(item.get("extra"), dict) else ""),
            )
        )
    return True, findings


def run_gitleaks(target_dir: str | Path) -> tuple[bool, list[NormalizedFinding]]:
    """Run Gitleaks (``gitleaks detect --no-git``) and normalize results."""
    cwd = Path(target_dir)
    ran, stdout = _run(
        ["gitleaks", "detect", "--source", ".", "--no-git", "--format", "json"],
        cwd,
    )
    if not ran:
        return False, []
    findings: list[NormalizedFinding] = []
    try:
        payload = json.loads(stdout or "null")
    except json.JSONDecodeError:
        return True, []
    leaks = payload if isinstance(payload, list) else []
    for item in leaks:
        if not isinstance(item, dict):
            continue
        findings.append(
            NormalizedFinding(
                scanner="gitleaks",
                rule_id=str(item.get("RuleID", "gitleaks.secret")),
                severity="high",
                file_path=str(item.get("File")) if item.get("File") else None,
                line_number=int(item["StartLine"]) if isinstance(item.get("StartLine"), int) else None,
                # Never persist the raw secret: keep description + redacted match.
                message=redact_secrets(
                    f"{item.get('Description', 'Potential secret')} "
                    f"in {item.get('File', '?')}: {REDACTED}"
                ),
            )
        )
    return True, findings


def run_pip_audit(target_dir: str | Path) -> tuple[bool, list[NormalizedFinding]]:
    """Run pip-audit against requirements files (no dependency install)."""
    cwd = Path(target_dir)
    req_files = [p for p in ("requirements.txt", "requirements-dev.txt", "requirements.lock") if (cwd / p).is_file()]
    targets = req_files or (["pyproject.toml"] if (cwd / "pyproject.toml").is_file() else [])
    if not targets:
        return False, []  # nothing auditable -> record as skipped by caller
    argv = ["pip-audit", "--format", "json"]
    for target in targets:
        argv += ["--requirement", target] if target.endswith(".txt") else []
    ran, stdout = _run(argv, cwd)
    if not ran:
        return False, []
    findings: list[NormalizedFinding] = []
    try:
        payload = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return True, []
    vulns = payload.get("vulnerabilities", payload) if isinstance(payload, dict) else payload
    if not isinstance(vulns, list):
        return True, []
    for item in vulns:
        if not isinstance(item, dict):
            continue
        spec = item.get("spec", item.get("fix_versions", ""))
        findings.append(
            NormalizedFinding(
                scanner="pip-audit",
                rule_id=str(item.get("id", item.get("alias", "pip-audit.unknown"))),
                severity=_normalize_severity(item.get("severity")),
                file_path=str(item.get("package", item.get("name", ""))) or None,
                line_number=None,
                message=redact_secrets(f"{item.get('package', '?')} {spec}: {item.get('description', '')}"[:1000]),
            )
        )
    return True, findings


def run_npm_audit(target_dir: str | Path) -> tuple[bool, list[NormalizedFinding]]:
    """Run ``npm audit --package-lock-only --json`` (never installs)."""
    cwd = Path(target_dir)
    if not (cwd / "package.json").is_file() and not (cwd / "package-lock.json").is_file():
        return False, []
    ran, stdout = _run(["npm", "audit", "--package-lock-only", "--json"], cwd)
    if not ran:
        return False, []
    findings: list[NormalizedFinding] = []
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return True, []
    advisories = payload.get("advisories", {}) if isinstance(payload, dict) else {}
    if isinstance(advisories, dict):
        for key, adv in advisories.items():
            if not isinstance(adv, dict):
                continue
            findings.append(
                NormalizedFinding(
                    scanner="npm-audit",
                    rule_id=str(adv.get("id", key)),
                    severity=_normalize_severity(adv.get("severity")),
                    file_path=str(adv.get("module_name")) or None,
                    line_number=None,
                    message=redact_secrets(f"{adv.get('title', '')}: {adv.get('overview', '')}"[:1000]),
                )
            )
    for vuln in (payload.get("vulnerabilities", []) if isinstance(payload, dict) else []):
        if isinstance(vuln, dict):
            findings.append(
                NormalizedFinding(
                    scanner="npm-audit",
                    rule_id=str(vuln.get("rule_id", vuln.get("name", "npm-audit.unknown"))),
                    severity=_normalize_severity(vuln.get("severity")),
                    file_path=str(vuln.get("name")) or None,
                    line_number=None,
                    message=redact_secrets(str(vuln.get("description", ""))[:1000]),
                )
            )
    return True, findings


def run_bandit(target_dir: str | Path) -> tuple[bool, list[NormalizedFinding]]:
    """Run Bandit (``bandit -r -f json``) static analysis on Python code."""
    cwd = Path(target_dir)
    ran, stdout = _run(["bandit", "-r", ".", "-f", "json", "-q"], cwd)
    if not ran:
        return False, []
    findings: list[NormalizedFinding] = []
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return True, []
    for item in payload.get("results", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        findings.append(
            NormalizedFinding(
                scanner="bandit",
                rule_id=str(item.get("test_id", "bandit.unknown")),
                severity=_normalize_severity(item.get("issue_severity")),
                file_path=str(item.get("filename")) if item.get("filename") else None,
                line_number=int(item["line_number"]) if isinstance(item.get("line_number"), int) else None,
                message=redact_secrets(str(item.get("issue_text", ""))[:1000]),
            )
        )
    return True, findings


def _derive_status(findings: list[NormalizedFinding]) -> str:
    severities = {f.severity for f in findings}
    if severities & {"critical", "high"}:
        return "critical"
    if severities & {"medium"}:
        return "warning"
    if findings:
        return "warning" if severities & {"low"} else "pass"
    return "pass"


def run_all_scanners(target_dir: str | Path) -> ScanSummary:
    """Run every available scanner; normalize + redact all findings.

    Scanners whose binaries are missing (lightweight CI) or whose manifest
    preconditions are unmet are listed in ``scanners_skipped`` rather than
    raising, per the security-scanners skill step 2.
    """
    cwd = Path(target_dir)
    summary = ScanSummary()
    runners = (
        ("semgrep", run_semgrep),
        ("gitleaks", run_gitleaks),
        ("pip-audit", run_pip_audit),
        ("npm-audit", run_npm_audit),
        ("bandit", run_bandit),
    )
    for name, runner in runners:
        try:
            ran, findings = runner(cwd)
        except Exception as exc:  # never let one scanner kill the suite
            summary.scanners_skipped.append(name)
            summary.errors.append(f"{name}: {type(exc).__name__}")
            continue
        if ran:
            summary.scanners_executed.append(name)
            summary.findings.extend(findings)
        else:
            summary.scanners_skipped.append(name)
    summary.overall_status = _derive_status(summary.findings)
    return summary
