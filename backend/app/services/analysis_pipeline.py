"""Deterministic analysis pipeline orchestration (Track 3).

Stages: GitHub inspect → diary discovery → security scan → deployment
check → agent evaluation (via injected stub/protocol callables) →
persistence of an immutable commit-linked snapshot.

Non-negotiable invariants enforced here:
    - Advisory & read-only: user repositories are only cloned/inspected.
    - Two dimensions: ``dev_completion_pct`` is computed ONLY from
      development-milestone statuses and MUST NOT modify
      ``ai_proposed_points`` / ``human_override_points``.
    - Score preservation: new ``criterion_assessments`` rows carry fresh AI
      proposals; human overrides from prior runs are never overwritten —
      this module never writes ``human_override_*`` on existing rows.

Agent invocation uses dependency-injected callables defaulting to
deterministic offline stubs (``needs_review`` / low confidence), so the
pipeline runs in CI without a Gemini key. Track 2 agents can be wired by
passing real callables.
"""

from __future__ import annotations

import logging
import re
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.deployment_monitor import check_deployment_health, discover_deployment_url
from app.services.diary_service import discover_and_read
from app.services.github_service import (
    fetch_repo_metadata,
    get_clone_head_sha,
    shallow_clone_context,
)
from app.services.security_scanner import ScanSummary, redact_secrets, run_all_scanners

logger = logging.getLogger(__name__)

ADVISORY_NOTICE = (
    "AI estimates are advisory only and never constitute an official course grade."
)

_GEMINI_DIAG_METHOD = "generateContent"
_GEMINI_DIAG_MAX_LEN = 500
_STATUS_CODE_RE = re.compile(r"\b(400|401|403|404|408|429|500|502|503|504|529)\b")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_APIKEY_RE = re.compile(r"AIza[0-9A-Za-z_~-]{10,}")


def _redact_text(text: str) -> str:
    """Redact secret/email material before logging or persisting."""
    value = str(text or "")
    try:
        value = redact_secrets(value)
    except Exception:
        pass
    try:
        value = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
        value = _BEARER_RE.sub("Bearer [REDACTED]", value)
        value = _APIKEY_RE.sub("[REDACTED]", value)
    except Exception:
        pass
    return value


def _extract_status_code(exc: BaseException | None) -> str | None:
    """Best-effort HTTP status/code from an exception chain (no secrets)."""
    current: BaseException | None = exc
    seen: list[str] = []
    depth = 0
    while current is not None and depth < 4:
        for attr in ("status", "status_code", "code", "http_status"):
            try:
                candidate = getattr(current, attr, None)
                if isinstance(candidate, int) and 100 <= candidate <= 599:
                    return str(candidate)
                if isinstance(candidate, str) and candidate.isdigit():
                    code = int(candidate)
                    if 100 <= code <= 599:
                        return str(code)
            except Exception:
                pass
        try:
            seen.append(str(current))
        except Exception:
            pass
        current = getattr(current, "__cause__", None) or getattr(
            current, "__context__", None
        )
        depth += 1
        if current is exc:
            break
    try:
        match = _STATUS_CODE_RE.search(" | ".join(seen))
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def _safe_gemini_model_name() -> str:
    """Model name only (never the key); 'unknown' when unresolvable."""
    try:
        from app.agents.base import get_gemini_model  # type: ignore  # read-only

        name = str(get_gemini_model() or "").strip()
        return name or "unknown"
    except Exception:
        return "unknown"


def _build_scorer_fallback_diagnostic(
    exc: BaseException | None,
    *,
    latency_ms: float | None = None,
) -> str:
    """Single-line redacted scorer-fallback diagnostic (<=500 chars)."""
    code = _extract_status_code(exc) if exc is not None else None
    model = _safe_gemini_model_name()
    excerpt = _redact_text(str(exc)[:500] if exc is not None else "")
    excerpt = re.sub(r"\s+", " ", excerpt).strip()[:200]
    latency_part = (
        f" latency_ms={int(latency_ms)}"
        if isinstance(latency_ms, (int, float)) and latency_ms >= 0
        else ""
    )
    code_part = code or (type(exc).__name__ if exc is not None else "unknown")
    base = (
        f"Gemini {code_part} {model} ({_GEMINI_DIAG_METHOD}){latency_part} "
        f"— using fallback needs_review."
    )
    if excerpt and excerpt not in base:
        base = f"{base} Excerpt: {excerpt}"
    return _redact_text(base)[:_GEMINI_DIAG_MAX_LEN]


# ---------------------------------------------------------------------------
# Pure helpers (import-safe, unit-testable without a DB)
# ---------------------------------------------------------------------------

def compute_dev_completion_pct(statuses: Sequence[str]) -> float:
    """Compute dev completion % from development-milestone statuses only.

    ``completed`` = 1.0, ``partial`` = 0.5, ``outstanding`` = 0.0. This value
    feeds ``analysis_runs.dev_completion_pct`` exclusively and must never be
    used to derive ``ai_proposed_points`` / ``human_override_points``.
    """
    if not statuses:
        return 0.0
    weights = {"completed": 1.0, "partial": 0.5, "outstanding": 0.0}
    total = sum(weights.get(str(s).lower(), 0.0) for s in statuses)
    return round(total / len(statuses) * 100.0, 2)


def effective_points(ai_proposed: int, human_override: int | None) -> int:
    """Derived score: human override wins, AI proposal otherwise."""
    return human_override if human_override is not None else ai_proposed


# ---------------------------------------------------------------------------
# Pipeline data structures
# ---------------------------------------------------------------------------

@dataclass
class PipelineEvidence:
    evidence_type: str
    title: str
    path_or_url: str
    snippet: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Everything the worker needs to persist one analysis snapshot."""

    commit_sha: str | None
    previous_commit_sha: str | None
    dev_completion_pct: float
    summary_markdown: str
    stalled_flag: bool = False
    scope_creep_flag: bool = False
    evidence: list[PipelineEvidence] = field(default_factory=list)
    diary_path: str | None = None
    diary_excerpt: str = ""
    security: ScanSummary | None = None
    deployment: dict[str, Any] = field(default_factory=dict)
    score_proposals: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Deterministic agent stubs (offline-safe defaults)
# ---------------------------------------------------------------------------

def stub_score_proposals(
    criteria: Sequence[dict[str, Any]], evidence: Sequence[PipelineEvidence]
) -> list[dict[str, Any]]:
    """Fallback scorer: every criterion ``estimated=0 / needs_review``.

    Used when Gemini agents are unavailable. Never invents points and never
    touches human overrides.
    """
    proposals = []
    for criterion in criteria:
        proposals.append(
            {
                "criterion_code": criterion.get("code", "unknown"),
                "max_points": int(criterion.get("max_points", 0) or 0),
                "ai_proposed_points": 0,
                "ai_reasoning": (
                    "Deterministic fallback: agent evaluation unavailable; "
                    "manual review required. " + ADVISORY_NOTICE
                ),
                "ai_confidence": 0.0,
                "score_state": "needs_review",
                "missing_for_next_level": "Run AI evaluation with repository evidence.",
                "evidence_paths": [e.path_or_url for e in evidence[:5]],
            }
        )
    return proposals


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_analysis_stages(
    *,
    github_repo_url: str,
    diary_override: str | None = None,
    deployment_override: str | None = None,
    dev_statuses: Sequence[str] = (),
    criteria: Sequence[dict[str, Any]] = (),
    previous_commit_sha: str | None = None,
    score_fn: Callable[..., list[dict[str, Any]]] | None = None,
    clone_url_for_offline_tests: str | None = None,
) -> PipelineResult:
    """Execute deterministic inspection stages for one project snapshot.

    Args:
        github_repo_url: Validated public GitHub URL.
        diary_override: Manual ``diary_path`` override (or None).
        deployment_override: Manual ``deployment_url`` override (or None).
        dev_statuses: Current development-milestone statuses for the
            ``dev_completion_pct`` dimension (never affects scores).
        criteria: Rubric criteria dicts for the scorer callable.
        previous_commit_sha: Prior run's SHA for stall/change comparison.
        score_fn: ``(criteria, evidence) -> proposals``; defaults to the
            deterministic stub. Track 2 wires real agents here.
        clone_url_for_offline_tests: Internal hook — pre-cloned directory to
            inspect instead of hitting the network (tests only).

    Returns:
        :class:`PipelineResult` ready for the worker to persist.
    """
    evidence: list[PipelineEvidence] = []
    commit_sha: str | None = None
    diary_path: str | None = None
    diary_excerpt = ""
    security: ScanSummary | None = None
    deployment: dict[str, Any] = {}
    error: str | None = None

    try:
        if clone_url_for_offline_tests is not None:
            _inspect_checkout(
                Path(clone_url_for_offline_tests),
                diary_override,
                deployment_override,
                evidence,
            )
            commit_sha = get_clone_head_sha(clone_url_for_offline_tests)
            diary_snapshot = discover_and_read(
                clone_url_for_offline_tests, manual_override=diary_override
            )
            diary_path, diary_excerpt = diary_snapshot.discovered_path, diary_snapshot.content_excerpt[:2000]
            security = run_all_scanners(clone_url_for_offline_tests)
        else:
            metadata = fetch_repo_metadata(github_repo_url)
            evidence.append(
                PipelineEvidence(
                    evidence_type="commit",
                    title=f"{metadata.owner}/{metadata.repo} default branch {metadata.default_branch}",
                    path_or_url=f"https://github.com/{metadata.owner}/{metadata.repo}",
                    metadata={"stars": metadata.stars, "workflows": metadata.workflows},
                )
            )
            for wf in metadata.workflows:
                evidence.append(
                    PipelineEvidence(
                        evidence_type="ci_workflow",
                        title=f"GitHub Actions workflow: {wf}",
                        path_or_url=f"https://github.com/{metadata.owner}/{metadata.repo}/blob/{metadata.default_branch}/.github/workflows/{wf}",
                    )
                )
            with shallow_clone_context(github_repo_url) as clone:
                commit_sha = clone.commit_sha
                _inspect_checkout(clone.path, diary_override, deployment_override, evidence)
                diary_snapshot = discover_and_read(clone.path, manual_override=diary_override)
                diary_path = diary_snapshot.discovered_path
                diary_excerpt = diary_snapshot.content_excerpt[:2000]
                security = run_all_scanners(clone.path)
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
        logger.warning("Analysis inspection stage failed (%s).", type(exc).__name__)

    # Deployment check runs regardless of clone outcome (URL may be manual).
    # Deduplicate: _inspect_checkout already records the manual-override
    # deployment evidence, so skip adding a second entry for the same URL.
    try:
        target: str | None = deployment_override
        source = "manual"
        if target:
            from app.services.deployment_monitor import validate_target_url

            try:
                validate_target_url(target)
            except Exception:
                target = None
        if target:
            already_recorded = any(
                e.evidence_type == "deployment_url" and e.path_or_url == target
                for e in evidence
            )
            health = check_deployment_health(target)
            deployment = {"target_url": target, "discovery_source": source, **health.to_dict()}
            if not already_recorded:
                evidence.append(
                    PipelineEvidence(
                        evidence_type="deployment_url",
                        title=f"Deployment check: {target}",
                        path_or_url=target,
                        metadata={"http_status": health.http_status_code},
                    )
                )
    except Exception as exc:
        logger.warning("Deployment stage failed (%s).", type(exc).__name__)

    if security is not None:
        evidence.append(
            PipelineEvidence(
                evidence_type="security_report",
                title=f"Security scan: {len(security.findings)} findings ({security.overall_status})",
                path_or_url="scanners: " + ",".join(security.scanners_executed),
            )
        )
    if diary_path:
        evidence.append(
            PipelineEvidence(
                evidence_type="diary_entry",
                title=f"Diary: {diary_path}",
                path_or_url=diary_path,
                snippet=diary_excerpt[:500],
            )
        )

    dev_pct = compute_dev_completion_pct(dev_statuses)
    scorer = score_fn or stub_score_proposals
    scorer_started = time.perf_counter()
    try:
        proposals = scorer(criteria, evidence)
    except Exception as exc:
        latency_ms = (time.perf_counter() - scorer_started) * 1000.0
        diagnostic = _build_scorer_fallback_diagnostic(exc, latency_ms=latency_ms)
        logger.warning(
            "Scorer failed (%s model=%s method=%s latency_ms=%d); %s",
            type(exc).__name__,
            _safe_gemini_model_name(),
            _GEMINI_DIAG_METHOD,
            int(latency_ms),
            diagnostic,
        )
        proposals = stub_score_proposals(criteria, evidence)
        if error is None:
            error = diagnostic
        elif diagnostic not in error:
            error = (error + " | " + diagnostic)[:_GEMINI_DIAG_MAX_LEN]

    stalled = previous_commit_sha is not None and commit_sha is not None and previous_commit_sha == commit_sha
    summary = _build_summary(
        commit_sha, diary_path, security, deployment, dev_pct, proposals, error
    )
    return PipelineResult(
        commit_sha=commit_sha,
        previous_commit_sha=previous_commit_sha,
        dev_completion_pct=dev_pct,  # dimension 1: never mapped to points
        summary_markdown=summary,
        stalled_flag=bool(stalled),
        scope_creep_flag=False,
        evidence=evidence,
        diary_path=diary_path,
        diary_excerpt=diary_excerpt,
        security=security,
        deployment=deployment,
        score_proposals=proposals,  # dimension 2: advisory estimates only
        error=error,
    )


def _record_file_evidence(
    checkout: Path,
    rel: str,
    kind: str,
    evidence: list[PipelineEvidence],
    seen: set[tuple[str, str]],
    *,
    max_chars: int = 500,
) -> None:
    """Best-effort static read of one checkout-relative file (never executed).

    Appends a single :class:`PipelineEvidence` when the file exists. Skips
    silently when missing/unreadable. ``seen`` dedupes ``(kind, rel)`` pairs
    so re-inspection stays idempotent within one run. Snippets are bounded
    to ``max_chars`` and the evidence ``kind`` is coerced at persist time
    via :func:`_evidence_type` to an allowed ``EvidenceType`` Enum value.
    """
    key = (kind, rel)
    if key in seen:
        return
    path = checkout / rel
    try:
        if not path.is_file():
            return
    except OSError:
        return
    try:
        snippet = path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError:
        snippet = None
    seen.add(key)
    evidence.append(
        PipelineEvidence(
            evidence_type=kind,
            title=f"{kind}: {rel}",
            path_or_url=rel,
            snippet=snippet,
        )
    )


def _record_readme_quickstart(
    checkout: Path,
    evidence: list[PipelineEvidence],
    seen: set[tuple[str, str]],
) -> None:
    """Record the README quickstart/single-command section (static read only).

    Idempotent via ``seen`` key ``("readme", "README.md#quickstart")`` so it
    never duplicates the full-file ``("readme", "README.md")`` entry.
    Snippet is bounded to 500 chars. Best-effort: silently skips when
    README.md is missing/unreadable or has no quickstart markers.
    """
    key = ("readme", "README.md#quickstart")
    if key in seen:
        return
    path = checkout / "README.md"
    try:
        if not path.is_file():
            return
    except OSError:
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    lowered = text.lower()
    markers = (
        "quickstart",
        "quick start",
        "getting started",
        "docker compose up",
        "single-command",
        "single command",
    )
    idx = -1
    for marker in markers:
        idx = lowered.find(marker)
        if idx != -1:
            break
    if idx == -1:
        return
    start = max(0, idx - 120)
    snippet = text[start : start + 500]
    seen.add(key)
    evidence.append(
        PipelineEvidence(
            evidence_type="readme",
            title="README quickstart (single-command): README.md#quickstart",
            path_or_url="README.md#quickstart",
            snippet=snippet,
        )
    )


def _record_glob_evidence(
    checkout: Path,
    pattern: str,
    kind: str,
    evidence: list[PipelineEvidence],
    seen: set[tuple[str, str]],
    *,
    limit: int = 20,
) -> None:
    """Record every file matching ``pattern`` as ``kind`` (static, bounded).

    Best-effort: missing directories / unreadable files are skipped.
    Idempotent via ``seen`` (``(kind, rel)`` pairs in
    :func:`_record_file_evidence`). Snippets bounded to 500 chars.
    """
    try:
        matches = sorted(checkout.glob(pattern))
    except Exception:
        return
    for match in matches[:limit]:
        try:
            if not match.is_file():
                continue
            rel = match.relative_to(checkout).as_posix()
        except (OSError, ValueError):
            continue
        _record_file_evidence(checkout, rel, kind, evidence, seen)


def _inspect_checkout(
    checkout: Path,
    diary_override: str | None,
    deployment_override: str | None,
    evidence: list[PipelineEvidence],
) -> None:
    """Collect static file evidence from a checkout (no code executed)."""
    interesting = (
        ("README.md", "readme"),
        ("readme.md", "readme"),
        ("docker-compose.yml", "docker_compose"),
        ("docker-compose.yaml", "docker_compose"),
        (".github/workflows", "ci_workflow"),
    )
    seen: set[tuple[str, str]] = set()
    for name, kind in interesting:
        path = checkout / name
        if path.exists():
            seen.add((kind, name))
            if path.is_dir():
                for child in sorted(path.iterdir())[:20]:
                    key = (kind, f"{name}/{child.name}")
                    if key in seen:
                        continue
                    seen.add(key)
                    evidence.append(
                        PipelineEvidence(
                            evidence_type=kind,
                            title=f"Workflow: {child.name}",
                            path_or_url=f".github/workflows/{child.name}",
                        )
                    )
            else:
                try:
                    snippet = path.read_text(encoding="utf-8", errors="replace")[:500]
                except OSError:
                    snippet = None
                evidence.append(
                    PipelineEvidence(
                        evidence_type=kind, title=name, path_or_url=name, snippet=snippet
                    )
                )
    # Phase 1 evidence-bundle fix: index agent-team + product docs already
    # present in the checkout so rubric criteria (context_management,
    # agent_team_spec) have citable evidence without new product code.
    # All reads are static (never executed), snippets bounded to 500 chars,
    # kinds limited to allowed EvidenceType values (coerced in
    # _persist_evidence_items via _evidence_type), and deduped per run.
    for rel in (
        "AGENTS.md",
        "backend/AGENTS.md",
        "backend/app/agents/AGENTS.md",
        "docs/specs/AGENT_TEAM_SPEC.md",
    ):
        _record_file_evidence(checkout, rel, "agent_config", evidence, seen)
    for pattern in (".agents/skills/*/SKILL.md", ".agents/agents/*.md"):
        try:
            matches = sorted(checkout.glob(pattern))
        except Exception:
            matches = []
        for match in matches[:20]:
            try:
                rel = match.relative_to(checkout).as_posix()
            except ValueError:
                continue
            _record_file_evidence(checkout, rel, "agent_config", evidence, seen)
    for rel in ("docs/PRODUCT_SPEC.md", "README.md"):
        _record_file_evidence(checkout, rel, "documentation", evidence, seen)
    for rel in ("docs/DIARY.md",):
        _record_file_evidence(checkout, rel, "diary_entry", evidence, seen)
    # Evidence-bundle extension for offline/fallback scoring: index
    # testing, container, CI, and observability signals already present in
    # the checkout so keyword fallback can cite them without Gemini.
    # All reads are static (never executed), snippets bounded to 500 chars
    # via _record_file_evidence, kinds limited to allowed EvidenceType
    # values (coerced at persist time via _evidence_type), and deduped per
    # run via `seen`. Missing paths are skipped (user-repo safe).
    for rel in (
        "pytest.ini",
        "playwright.config.ts",
        "frontend/playwright.config.ts",
    ):
        _record_file_evidence(checkout, rel, "test_result", evidence, seen)
    for pattern in ("backend/tests/*.py", "frontend/e2e/*"):
        _record_glob_evidence(checkout, pattern, "test_result", evidence, seen)
    for pattern in ("docker-compose*.yml", "docker-compose*.yaml"):
        _record_glob_evidence(checkout, pattern, "docker_compose", evidence, seen)
    for rel in ("Dockerfile", "backend/Dockerfile", "frontend/Dockerfile"):
        _record_file_evidence(checkout, rel, "docker_compose", evidence, seen)
    _record_glob_evidence(checkout, "*/Dockerfile", "docker_compose", evidence, seen)
    for pattern in (
        "infra/prometheus/**/*",
        "infra/grafana/**/*",
        "infra/loki/**/*",
        "infra/tempo/**/*",
    ):
        _record_glob_evidence(
            checkout, pattern, "observability_config", evidence, seen
        )
    # Bounded on-call agent: indexed both as agent_config (team topology)
    # and source_file (implementation evidence); distinct `seen` keys so
    # both rows persist idempotently.
    for kind in ("agent_config", "source_file"):
        _record_file_evidence(
            checkout, "backend/app/agents/oncall_agent.py", kind, evidence, seen
        )
    # README quickstart single-command section as readme/deployment_url hint.
    _record_readme_quickstart(checkout, evidence, seen)
    # Deployment discovery from checkout (manual override wins inside helper).
    # When a manual deployment_override is set, the caller (run_analysis_stages)
    # records the single manual-override evidence entry — skip checkout
    # discovery here to avoid a duplicate second entry.
    if deployment_override and deployment_override.strip():
        return
    try:
        url, source = discover_deployment_url(checkout, manual_override=deployment_override)
        if url:
            health = check_deployment_health(url)
            # stored by caller; record evidence-level metadata via closure list
            evidence.append(
                PipelineEvidence(
                    evidence_type="deployment_url",
                    title=f"Discovered deployment ({source}): {url}",
                    path_or_url=url,
                    metadata={"http_status": health.http_status_code},
                )
            )
    except Exception:
        pass  # discovery is best-effort


def _build_summary(
    commit_sha: str | None,
    diary_path: str | None,
    security: ScanSummary | None,
    deployment: dict[str, Any],
    dev_pct: float,
    proposals: list[dict[str, Any]],
    error: str | None,
) -> str:
    lines = [
        "# DevTrack AI Analysis Snapshot",
        "",
        f"- Commit: `{commit_sha or 'unknown'}`",
        f"- Development completion: {dev_pct:.1f}% (task dimension; not a grade)",
        f"- Diary: {diary_path or 'not found'}",
    ]
    if security is not None:
        lines.append(
            f"- Security: {security.overall_status} "
            f"({len(security.findings)} findings; "
            f"scanners: {', '.join(security.scanners_executed) or 'none'})"
        )
    if deployment:
        lines.append(
            f"- Deployment: {deployment.get('target_url')} "
            f"(reachable={deployment.get('is_reachable')}, "
            f"status={deployment.get('http_status_code')})"
        )
    estimated = sum(int(p.get("ai_proposed_points", 0) or 0) for p in proposals)
    lines.append(f"- Advisory estimated points: {estimated} ({ADVISORY_NOTICE})")
    if error:
        lines.append(f"- Inspection warning: {error}")
    lines.append("")
    return "\n".join(lines)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def persist_pipeline_result(
    session: Any,
    *,
    analysis_run_id: UUID,
    project_id: UUID,
    result: PipelineResult,
    max_total_points: int = 24,
) -> None:
    """Persist a :class:`PipelineResult` onto ORM rows (worker-owned writes).

    Updates ONLY the run's own snapshot columns (``commit_sha``,
    ``dev_completion_pct``, totals derived from the run's NEW proposals,
    summary, flags) and writes the run's child snapshot rows:
    ``evidence_items``, ``criterion_assessments``, ``diary_snapshots``,
    ``security_reports`` + ``security_findings``, ``deployment_checks``,
    and ``recommendations``. Never writes ``human_override_*`` and never
    mutates prior runs' ``criterion_assessments`` — score preservation
    invariant.

    Child sections are independent best-effort blocks: one section's
    failure is logged (class name only) and the remaining sections still
    persist, so a single bad row can never again produce a
    ``completed`` run with zero child rows silently. Re-persisting the
    same run first clears that run's prior child rows (idempotent).

    ``session`` is duck-typed (SQLAlchemy Session) to avoid hard cross-track
    imports; ORM classes are resolved lazily by name.
    """
    run = session.get(_model(session, "AnalysisRun"), analysis_run_id)
    if run is None:
        raise ValueError(f"analysis_run {analysis_run_id} not found.")
    run.commit_sha = result.commit_sha
    run.previous_commit_sha = result.previous_commit_sha
    # Dimension 1 — task completion only.
    run.dev_completion_pct = result.dev_completion_pct
    # Dimension 2 — advisory estimates from THIS run's proposals only.
    run.estimated_total_points = sum(
        int(p.get("ai_proposed_points", 0) or 0) for p in result.score_proposals
    )
    run.verified_total_points = sum(
        int(p.get("ai_proposed_points", 0) or 0)
        for p in result.score_proposals
        if p.get("score_state") == "verified"
    )
    run.max_total_points = max_total_points
    run.summary_markdown = result.summary_markdown
    run.stalled_flag = result.stalled_flag
    run.scope_creep_flag = result.scope_creep_flag
    if result.error and not result.commit_sha:
        run.status = _status(session, "failed")
        run.error_message = result.error
    session.flush()

    # Child snapshot rows (idempotent: clear this run's prior children first).
    _delete_run_children(session, analysis_run_id)
    evidence_ids = _persist_evidence_items(
        session, analysis_run_id=analysis_run_id, project_id=project_id, result=result
    )
    _persist_criterion_assessments(
        session,
        analysis_run_id=analysis_run_id,
        project_id=project_id,
        result=result,
        evidence_ids=evidence_ids,
    )
    _persist_diary_snapshot(
        session, analysis_run_id=analysis_run_id, project_id=project_id, result=result
    )
    _persist_security_report(
        session, analysis_run_id=analysis_run_id, project_id=project_id, result=result
    )
    _persist_deployment_check(
        session, analysis_run_id=analysis_run_id, project_id=project_id, result=result
    )
    _persist_recommendations(
        session,
        analysis_run_id=analysis_run_id,
        project_id=project_id,
        result=result,
        evidence_ids=evidence_ids,
    )
    session.flush()


def _delete_run_children(session: Any, analysis_run_id: UUID) -> None:
    """Remove this run's prior child rows so re-persist stays idempotent."""
    try:
        from app.models.models import (  # type: ignore  # read-only type use
            CriterionAssessment,
            DeploymentCheck,
            DiarySnapshot,
            EvidenceItem,
            Recommendation,
            SecurityFinding,
            SecurityReport,
        )

        for finding in (
            session.query(SecurityFinding)
            .join(SecurityReport, SecurityFinding.security_report_id == SecurityReport.id)
            .filter(SecurityReport.analysis_run_id == analysis_run_id)
            .all()
        ):
            session.delete(finding)
        for model, column in (
            (SecurityReport, SecurityReport.analysis_run_id),
            (Recommendation, Recommendation.analysis_run_id),
            (CriterionAssessment, CriterionAssessment.analysis_run_id),
            (EvidenceItem, EvidenceItem.analysis_run_id),
            (DiarySnapshot, DiarySnapshot.analysis_run_id),
            (DeploymentCheck, DeploymentCheck.analysis_run_id),
        ):
            for row in session.query(model).filter(column == analysis_run_id).all():
                session.delete(row)
        session.flush()
    except Exception as exc:
        logger.warning("Child-row cleanup skipped (%s).", type(exc).__name__)


def _persist_evidence_items(
    session: Any, *, analysis_run_id: UUID, project_id: UUID, result: PipelineResult
) -> list[str]:
    """Write ``result.evidence`` to ``evidence_items``; return new id strings."""
    try:
        from app.models.models import EvidenceItem  # type: ignore
    except Exception as exc:
        logger.warning("Evidence persist skipped (%s).", type(exc).__name__)
        return []
    ids: list[str] = []
    try:
        rows = []
        for item in result.evidence or []:
            rows.append(
                EvidenceItem(
                    analysis_run_id=analysis_run_id,
                    project_id=project_id,
                    evidence_type=_evidence_type(item.evidence_type),
                    title=str(item.title or "evidence")[:255],
                    path_or_url=str(item.path_or_url or "")[:1024],
                    commit_sha=result.commit_sha,
                    snippet=(item.snippet or "")[:2000] or None,
                    metadata_json=dict(item.metadata or {}),
                )
            )
        session.add_all(rows)
        session.flush()
        ids = [str(r.id) for r in rows]
    except Exception as exc:
        logger.warning("Evidence persist failed (%s).", type(exc).__name__)
    return ids


def _persist_criterion_assessments(
    session: Any,
    *,
    analysis_run_id: UUID,
    project_id: UUID,
    result: PipelineResult,
    evidence_ids: list[str],
) -> None:
    """Write ``result.score_proposals`` to ``criterion_assessments``.

    Each proposal joins to its ``assessment_milestones`` row via
    ``rubric_criteria.code`` so the NOT NULL
    ``assessment_milestone_id`` FK is always satisfied. Proposals with no
    matching milestone are skipped (logged) rather than violating the FK.
    Never writes ``human_override_*``.
    """
    if not result.score_proposals:
        return
    try:
        from app.models.models import (  # type: ignore
            AssessmentMilestone,
            CriterionAssessment,
            RubricCriterion,
        )
    except Exception as exc:
        logger.warning("Scorecard persist skipped (%s).", type(exc).__name__)
        return
    try:
        milestone_by_code: dict[str, Any] = {}
        for milestone, code in (
            session.query(AssessmentMilestone, RubricCriterion.code)
            .join(
                RubricCriterion,
                AssessmentMilestone.rubric_criterion_id == RubricCriterion.id,
            )
            .filter(AssessmentMilestone.project_id == project_id)
            .all()
        ):
            milestone_by_code[str(code)] = milestone.id
    except Exception as exc:
        logger.warning("Scorecard milestone lookup failed (%s).", type(exc).__name__)
        return
    try:
        rows = []
        for proposal in result.score_proposals:
            code = str(proposal.get("criterion_code", "") or "")
            milestone_id = milestone_by_code.get(code)
            if milestone_id is None:
                logger.warning(
                    "Scorecard proposal skipped: no assessment milestone for code."
                )
                continue
            try:
                max_pts = int(proposal.get("max_points", 0) or 0)
            except (TypeError, ValueError):
                max_pts = 0
            try:
                proposed = int(proposal.get("ai_proposed_points", 0) or 0)
            except (TypeError, ValueError):
                proposed = 0
            proposed = max(0, min(proposed, max_pts)) if max_pts > 0 else max(0, proposed)
            try:
                confidence = float(proposal.get("ai_confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(confidence, 1.0))
            rows.append(
                CriterionAssessment(
                    analysis_run_id=analysis_run_id,
                    project_id=project_id,
                    assessment_milestone_id=milestone_id,
                    criterion_code=code,
                    max_points=max_pts,
                    ai_proposed_points=proposed,
                    ai_reasoning=str(proposal.get("ai_reasoning", "") or ""),
                    ai_confidence=confidence,
                    missing_for_next_level=proposal.get("missing_for_next_level"),
                    score_state=_score_state(proposal.get("score_state")),
                    evidence_ids=list(evidence_ids[:10]),
                )
            )
        session.add_all(rows)
        session.flush()
    except Exception as exc:
        logger.warning("Scorecard persist failed (%s).", type(exc).__name__)


def _persist_diary_snapshot(
    session: Any, *, analysis_run_id: UUID, project_id: UUID, result: PipelineResult
) -> None:
    """Write the discovered diary excerpt to ``diary_snapshots`` (if any)."""
    if not result.diary_path:
        return
    try:
        from app.models.models import DiarySnapshot  # type: ignore
    except Exception as exc:
        logger.warning("Diary persist skipped (%s).", type(exc).__name__)
        return
    try:
        excerpt = (result.diary_excerpt or "")[:2000]
        session.add(
            DiarySnapshot(
                analysis_run_id=analysis_run_id,
                project_id=project_id,
                discovered_path=str(result.diary_path)[:512],
                completed_work=[excerpt] if excerpt else [],
                blockers=[],
                decisions=[],
                next_steps=[],
                git_alignment_summary=(
                    f"Diary discovered at {result.diary_path}; "
                    f"commit {result.commit_sha or 'unknown'}."
                ),
                discrepancies=[],
            )
        )
        session.flush()
    except Exception as exc:
        logger.warning("Diary persist failed (%s).", type(exc).__name__)


def _persist_security_report(
    session: Any, *, analysis_run_id: UUID, project_id: UUID, result: PipelineResult
) -> None:
    """Write ``result.security`` to ``security_reports`` + ``security_findings``.

    Finding messages arrive pre-redacted from the scanner runner (secret
    values already ``[REDACTED]``); they are persisted as-is.
    """
    if result.security is None:
        return
    try:
        from app.models.models import SecurityFinding, SecurityReport  # type: ignore
    except Exception as exc:
        logger.warning("Security persist skipped (%s).", type(exc).__name__)
        return
    try:
        report = SecurityReport(
            analysis_run_id=analysis_run_id,
            project_id=project_id,
            commit_sha=result.commit_sha or "unknown",
            overall_status=_security_status(result.security.overall_status),
            scanners_executed=list(result.security.scanners_executed or []),
            ai_executive_summary=(
                f"Deterministic scan: {len(result.security.findings)} findings "
                f"({result.security.overall_status}); scanners: "
                f"{', '.join(result.security.scanners_executed) or 'none'}. "
                "Advisory only — see Security Reviewer guidance."
            ),
        )
        session.add(report)
        session.flush()
        findings = []
        for rank, finding in enumerate(result.security.findings or [], start=1):
            findings.append(
                SecurityFinding(
                    security_report_id=report.id,
                    scanner=str(finding.scanner or "unknown")[:64],
                    rule_id=str(finding.rule_id or "unknown")[:255],
                    severity=_severity(finding.severity),
                    file_path=finding.file_path,
                    line_number=finding.line_number,
                    raw_message=str(finding.message or ""),
                    priority_rank=rank,
                )
            )
        session.add_all(findings)
        session.flush()
    except Exception as exc:
        logger.warning("Security persist failed (%s).", type(exc).__name__)


def _persist_deployment_check(
    session: Any, *, analysis_run_id: UUID, project_id: UUID, result: PipelineResult
) -> None:
    """Write ``result.deployment`` to ``deployment_checks`` (if a target exists)."""
    target = (result.deployment or {}).get("target_url")
    if not target:
        return
    try:
        from app.models.models import DeploymentCheck  # type: ignore
    except Exception as exc:
        logger.warning("Deployment persist skipped (%s).", type(exc).__name__)
        return
    try:
        deployment = result.deployment or {}
        session.add(
            DeploymentCheck(
                project_id=project_id,
                analysis_run_id=analysis_run_id,
                target_url=str(target)[:512],
                discovery_source=_discovery_source(deployment.get("discovery_source")),
                is_reachable=bool(deployment.get("is_reachable", False)),
                http_status_code=deployment.get("http_status_code"),
                https_valid=bool(deployment.get("https_valid", False)),
                response_time_ms=deployment.get("response_time_ms"),
                error_detail=str(deployment.get("error_detail") or "")[:512] or None,
            )
        )
        session.flush()
    except Exception as exc:
        logger.warning("Deployment persist failed (%s).", type(exc).__name__)


def _persist_recommendations(
    session: Any,
    *,
    analysis_run_id: UUID,
    project_id: UUID,
    result: PipelineResult,
    evidence_ids: list[str],
) -> None:
    """Derive advisory next actions from score gaps (never official grades)."""
    gaps = []
    for proposal in result.score_proposals or []:
        try:
            max_pts = int(proposal.get("max_points", 0) or 0)
            proposed = int(proposal.get("ai_proposed_points", 0) or 0)
        except (TypeError, ValueError):
            continue
        gap = max_pts - proposed
        if gap > 0:
            gaps.append((gap, proposal))
    if not gaps:
        return
    try:
        from app.models.models import Recommendation  # type: ignore
    except Exception as exc:
        logger.warning("Recommendations persist skipped (%s).", type(exc).__name__)
        return
    try:
        gaps.sort(key=lambda item: item[0], reverse=True)
        rows = []
        for rank, (gap, proposal) in enumerate(gaps[:5], start=1):
            code = str(proposal.get("criterion_code", "unknown") or "unknown")
            rows.append(
                Recommendation(
                    analysis_run_id=analysis_run_id,
                    project_id=project_id,
                    rank=rank,
                    suggested_task=str(
                        proposal.get("missing_for_next_level")
                        or f"Advance {code} toward full points"
                    )[:255],
                    rationale=str(proposal.get("ai_reasoning", "") or "")[:2000]
                    or "Advisory recommendation derived from score gap.",
                    related_criterion_code=code,
                    potential_points_delta=int(gap),
                    priority=_recommendation_priority(gap),
                    estimated_effort_hours=None,
                    technical_risk=_risk_level("low"),
                    supporting_evidence_ids=list(evidence_ids[:10]),
                    is_completed=False,
                )
            )
        session.add_all(rows)
        session.flush()
    except Exception as exc:
        logger.warning("Recommendations persist failed (%s).", type(exc).__name__)


def _evidence_type(value: Any) -> Any:
    try:
        from app.schemas.enums import EvidenceType  # type: ignore

        try:
            return EvidenceType(str(value or "").lower())
        except ValueError:
            return EvidenceType.SOURCE_FILE
    except Exception:
        return value


def _score_state(value: Any) -> Any:
    try:
        from app.schemas.enums import ScoreState  # type: ignore

        state = getattr(value, "value", value)
        try:
            return ScoreState(str(state or "").lower())
        except ValueError:
            return ScoreState.NEEDS_REVIEW
    except Exception:
        return value


def _security_status(value: Any) -> Any:
    try:
        from app.schemas.enums import SecurityStatus  # type: ignore

        status = getattr(value, "value", value)
        try:
            return SecurityStatus(str(status or "").lower())
        except ValueError:
            return SecurityStatus.WARNING
    except Exception:
        return value


def _severity(value: Any) -> Any:
    try:
        from app.schemas.enums import SeverityLevel  # type: ignore

        level = getattr(value, "value", value)
        try:
            return SeverityLevel(str(level or "").lower())
        except ValueError:
            return SeverityLevel.INFO
    except Exception:
        return value


def _discovery_source(value: Any) -> Any:
    try:
        from app.schemas.enums import DeploymentDiscoverySource  # type: ignore

        source = getattr(value, "value", value)
        try:
            return DeploymentDiscoverySource(str(source or "").lower())
        except ValueError:
            return DeploymentDiscoverySource.MANUAL
    except Exception:
        return value


def _recommendation_priority(gap: int) -> Any:
    try:
        from app.schemas.enums import PriorityLevel  # type: ignore

        if gap >= 2:
            return PriorityLevel.HIGH
        if gap == 1:
            return PriorityLevel.MEDIUM
        return PriorityLevel.LOW
    except Exception:
        return "medium"


def _risk_level(value: Any) -> Any:
    try:
        from app.schemas.enums import RiskLevel  # type: ignore

        level = getattr(value, "value", value)
        try:
            return RiskLevel(str(level or "").lower())
        except ValueError:
            return RiskLevel.LOW
    except Exception:
        return value


def _model(session: Any, name: str) -> Any:
    """Resolve an ORM class without a hard cross-track import."""
    bind = getattr(session, "get_bind", None)
    registry = None
    try:
        from app.models.models import (  # type: ignore  # read-only type use
            AnalysisRun,
            AnalysisStatus,
        )

        if name == "AnalysisRun":
            return AnalysisRun
    except Exception:
        pass
    raise RuntimeError(f"ORM model {name} unavailable in this environment.")


def _status(session: Any, value: str) -> Any:
    try:
        from app.schemas.enums import AnalysisStatus  # type: ignore

        return AnalysisStatus(value)
    except Exception:
        return value
