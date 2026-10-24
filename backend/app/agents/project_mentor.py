"""Project Mentor / Orchestrator runtime agent (Track 2).

Synthesizes scorecard, progress, diary, security, and deployment signals into
an executive summary plus ranked high-ROI ``RecommendationItem`` entries.
Detects stalled development and scope creep versus the previous commit SHA.

Advisory only: recommendations reference ``related_criterion_code`` and
``potential_points_delta`` as estimates, never official grades.
"""

from __future__ import annotations

from typing import Any, Sequence

try:
    from app.agents.base import ADVISORY_NOTICE, run_with_fallback
except ImportError:  # harness imports as backend.app.*: fix sys.path first
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from app.agents.base import ADVISORY_NOTICE, run_with_fallback

from app.schemas.agent_outputs import (
    MentorEvaluationOutput,
    RecommendationItem,
)
from app.schemas.enums import PriorityLevel, RiskLevel

MENTOR_SYSTEM = (
    "You are DevTrack AI's Project Mentor and orchestrator. Synthesize the "
    "rubric scorecard, development progress, diary analysis, security review, "
    "and deployment status into a concise executive summary (Markdown) plus a "
    "ranked list of high-ROI next recommendations. Each recommendation links "
    "related_criterion_code, potential_points_delta (estimate), priority, "
    "estimated_effort_hours, technical_risk, and supporting evidence paths. "
    "Detect stalled development (no meaningful commits vs previous SHA) and "
    "scope creep (work drifting from rubric criteria). AI points are advisory "
    "estimates, never official course grades; preserve ai_proposed_points and "
    "ai_reasoning alongside any human override."
)


def _summarize_block(title: str, payload: Any, limit: int = 1500) -> str:
    if payload is None:
        return f"{title}: (not available)"
    try:
        if hasattr(payload, "model_dump_json"):
            text = payload.model_dump_json(indent=1)
        elif hasattr(payload, "model_dump"):
            import json as _json

            text = _json.dumps(payload.model_dump(), indent=1, default=str)
        else:
            text = str(payload)
    except Exception:
        text = str(payload)
    if len(text) > limit:
        text = text[:limit] + "... [truncated]"
    return f"{title}:\n{text}"


def fallback_mentor_evaluation(
    scorecard: Any = None,
    progress: Any = None,
    diary: Any = None,
    security: Any = None,
    deployment_status: str | None = None,
    previous_commit_sha: str | None = None,
    current_commit_sha: str | None = None,
    error: Exception | None = None,  # noqa: ARG001
) -> MentorEvaluationOutput:
    """Deterministic synthesis: generic high-ROI tasks, conservative flags."""
    same_sha = bool(
        previous_commit_sha and current_commit_sha
        and previous_commit_sha == current_commit_sha
    )
    # Extract lowest-confidence / unverified criteria if a scorecard is present.
    recs: list[RecommendationItem] = []
    try:
        evals: Sequence[Any] = []
        if hasattr(scorecard, "criteria_evaluations"):
            evals = scorecard.criteria_evaluations or []
        elif isinstance(scorecard, dict):
            evals = scorecard.get("criteria_evaluations", [])
        for i, ev in enumerate(list(evals)[:5], start=1):
            if isinstance(ev, dict):
                code = str(ev.get("criterion_code", "general"))
                max_pts = int(ev.get("max_points", 2))
                proposed = int(ev.get("ai_proposed_points", 0))
            else:
                code = str(getattr(ev, "criterion_code", "general"))
                max_pts = int(getattr(ev, "max_points", 2))
                proposed = int(getattr(ev, "ai_proposed_points", 0))
            delta = max(0, max_pts - proposed)
            recs.append(
                RecommendationItem(
                    rank=i,
                    suggested_task=f"Collect and document verifiable evidence for `{code}`",
                    rationale=(
                        f"Offline fallback: `{code}` shows {proposed}/{max_pts} "
                        f"(estimate); closing the gap is high-ROI."
                    ),
                    related_criterion_code=code,
                    potential_points_delta=delta,
                    priority=PriorityLevel.HIGH if delta > 0 else PriorityLevel.LOW,
                    estimated_effort_hours=3.0,
                    technical_risk=RiskLevel.LOW,
                    supporting_evidence_paths=[],
                )
            )
    except Exception:
        recs = []
    if not recs:
        recs = [
            RecommendationItem(
                rank=1,
                suggested_task="Establish README, spec, and CI baseline",
                rationale=(
                    "Offline fallback: no scorecard detail available; baseline "
                    "docs and CI unlock multiple criteria."
                ),
                related_criterion_code="general",
                potential_points_delta=0,
                priority=PriorityLevel.MEDIUM,
                estimated_effort_hours=4.0,
                technical_risk=RiskLevel.LOW,
                supporting_evidence_paths=[],
            )
        ]
    summary = (
        "# Mentor Snapshot (offline fallback)\n\n"
        "Deterministic synthesis — Gemini unavailable. "
        f"previous_sha={previous_commit_sha or 'n/a'} "
        f"current_sha={current_commit_sha or 'n/a'}; "
        f"stalled={'yes (identical SHAs)' if same_sha else 'not detected statically'}; "
        f"deployment={deployment_status or 'unknown'}. "
        + ADVISORY_NOTICE
    )
    return MentorEvaluationOutput(
        executive_summary_markdown=summary,
        stalled_flag=same_sha,
        scope_creep_flag=False,
        recommendations=recs,
    )


def evaluate_project(
    scorecard: Any = None,
    progress: Any = None,
    diary: Any = None,
    security: Any = None,
    deployment_status: str | None = None,
    previous_commit_sha: str | None = None,
    current_commit_sha: str | None = None,
    project_name: str = "",
) -> MentorEvaluationOutput:
    """Synthesize all specialist signals into mentor guidance."""

    def _prompt() -> tuple[str, str]:
        user = (
            f"Project: {project_name or '(unknown)'} | "
            f"previous_sha={previous_commit_sha or 'none'} "
            f"current_sha={current_commit_sha or 'unknown'}\n\n"
            + _summarize_block("SCORECARD (Rubric Analyst, advisory)", scorecard)
            + "\n\n" + _summarize_block("PROGRESS (Progress Analyst)", progress)
            + "\n\n" + _summarize_block("DIARY (Diary Analyst)", diary)
            + "\n\n" + _summarize_block("SECURITY (Security Reviewer)", security)
            + f"\n\nDEPLOYMENT STATUS: {deployment_status or 'unknown'}\n\n"
            "Return executive_summary_markdown, stalled_flag, scope_creep_flag, "
            "and ranked recommendations with criterion links and effort/risk."
        )
        return (MENTOR_SYSTEM, user)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=MentorEvaluationOutput,
        parse=lambda raw: MentorEvaluationOutput.model_validate(raw),
        fallback=lambda exc: fallback_mentor_evaluation(
            scorecard, progress, diary, security, deployment_status,
            previous_commit_sha, current_commit_sha, exc,
        ),
    )
