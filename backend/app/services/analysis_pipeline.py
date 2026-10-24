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
import sys
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
from app.services.security_scanner import ScanSummary, run_all_scanners

logger = logging.getLogger(__name__)

ADVISORY_NOTICE = (
    "AI estimates are advisory only and never constitute an official course grade."
)


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
    try:
        proposals = scorer(criteria, evidence)
    except Exception as exc:
        logger.warning("Scorer failed (%s); using stub.", type(exc).__name__)
        proposals = stub_score_proposals(criteria, evidence)

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
    for name, kind in interesting:
        path = checkout / name
        if path.exists():
            if path.is_dir():
                for child in sorted(path.iterdir())[:20]:
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
    summary, flags). Never writes ``human_override_*`` and never mutates
    prior runs' ``criterion_assessments`` — score preservation invariant.

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
