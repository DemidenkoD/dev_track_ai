"""Rubric Analyst runtime agent (Track 2).

Implements ``.agents/skills/rubric-evaluation/SKILL.md`` 5-step workflow:

1. **Load Versioned Official Rubric** — scoring levels come from the DB
   ``RubricCriterion`` records or ``docs/rubrics/ai_dev_tools_zoomcamp_2026.json``;
   never invented.
2. **Map Evidence Items First** — concrete evidence (commits, README, docs,
   workflows, docker-compose, tests, observability configs, deployment checks)
   is serialized into the prompt before any scoring call.
3. **Enforce Structured Output Schema** — ``ExtractedRubricOutput`` /
   ``ScorecardEvaluationOutput`` via ``response_schema``.
4. **Assign Score States Accurately** — ``verified`` only with concrete
   evidence; ``estimated`` for partial; ``needs_review`` + ``ai_confidence <
   0.70`` when ambiguous/unverifiable (e.g. live deployment behaviour).
5. **Preserve Human Overrides** — this agent only proposes
   ``ai_proposed_points``/``ai_reasoning``; it never writes
   ``human_override_points`` (Track 1 API preserves both side-by-side).

Advisory only: summaries always carry the advisory-not-official notice.
Deterministic fallback keeps CI green when GEMINI_API_KEY is missing.
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

try:
    from app.agents.base import ADVISORY_NOTICE, run_with_fallback
except ImportError:  # harness imports as backend.app.*: fix sys.path first
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from app.agents.base import ADVISORY_NOTICE, run_with_fallback

from app.schemas.agent_outputs import (
    CriterionScoreProposal,
    ExtractedCriterionItem,
    ExtractedRubricOutput,
    ScorecardEvaluationOutput,
    ScoringLevelItem,
)
from app.schemas.enums import EvidenceType, ScoreState

RUBRIC_ANALYST_SYSTEM = (
    "You are DevTrack AI's Rubric Analyst. You extract official course rubric "
    "criteria and evaluate repository evidence against each criterion's EXACT "
    "official scoring levels. Rules: (1) never invent scoring rules — use only "
    "the provided scoring_levels; (2) every score must cite concrete evidence "
    "paths/commit SHAs; (3) use score_state='verified' only with concrete "
    "unambiguous evidence, 'estimated' for partial/static evidence, and "
    "'needs_review' with ai_confidence below 0.70 when evidence is missing, "
    "contradictory, or needs live runtime verification; (4) you only propose "
    "ai_proposed_points and ai_reasoning — human overrides are preserved "
    "separately; (5) AI estimates are advisory, never official grades."
)

EXTRACTION_SYSTEM = (
    "You are DevTrack AI's Rubric Analyst (ingestion mode). Extract official "
    "criteria, point values, scoring levels, and passing thresholds from the "
    "provided raw rubric content (URL text / PDF text / Markdown / pasted text). "
    "Preserve official descriptions verbatim where possible. Never invent "
    "criteria not present in the source. Output strictly matches the schema."
)

# Heuristic keyword hints per official 2026 criterion used ONLY by the
# deterministic offline fallback (live Gemini path uses real evidence text).
_FALLBACK_KEYWORDS: dict[str, list[str]] = {
    "problem_description": ["readme", "problem", "motivation", "audience"],
    "product_specification": ["spec", "product_spec", "architecture", "requirements"],
    "agent_team_specification": ["agent", "aglets", ".agents", "skills"],
    "context_management": ["agents.md", "skills", "context"],
    "application": ["frontend", "backend", "database", "app"],
    "testing": ["test", "pytest", "playwright", "vitest"],
    "containerization": ["dockerfile", "docker-compose", "compose"],
    "deployment": ["deploy", "https", "url", "health"],
    "ci_cd": ["github/workflows", ".github", "ci", "cd", "pipeline"],
    "observability": ["opentelemetry", "prometheus", "loki", "tempo", "grafana", "otel"],
    "alerting_on_user_impact": ["alert", "sli", "5xx", "latency", "pagerduty", "alertmanager"],
    "on_call_agent": ["on-call", "oncall", "runbook", "incident"],
}

_LIVE_VERIFICATION_CODES = {"deployment", "alerting_on_user_impact", "on_call_agent"}


def _evidence_to_bullets(evidence_items: Sequence[Any]) -> str:
    """Serialize evidence records (Step 2: map evidence first)."""
    if not evidence_items:
        return "(no evidence items collected for this run)"
    lines: list[str] = []
    for ev in evidence_items:
        if isinstance(ev, dict):
            etype = ev.get("evidence_type", "?")
            path = ev.get("path_or_url", "?")
            title = ev.get("title", "")
            sha = ev.get("commit_sha") or ""
            snippet = (ev.get("snippet") or "")[:400]
            lines.append(f"- [{etype}] {title} @ {path} (sha={sha}): {snippet}")
        else:
            etype = getattr(ev, "evidence_type", "?")
            path = getattr(ev, "path_or_url", "?")
            title = getattr(ev, "title", "")
            sha = getattr(ev, "commit_sha", None) or ""
            snippet = (getattr(ev, "snippet", None) or "")[:400]
            lines.append(f"- [{etype}] {title} @ {path} (sha={sha}): {snippet}")
    return "\n".join(lines)


def _criteria_to_prompt_block(criteria: Sequence[Any]) -> str:
    """Render official scoring levels verbatim (Step 1: no invented rules)."""
    blocks: list[str] = []
    for c in criteria:
        if isinstance(c, dict):
            code = c.get("code", "?")
            name = c.get("name", code)
            max_pts = c.get("max_points", 0)
            desc = c.get("description", "")
            levels = c.get("scoring_levels", [])
            level_lines = [
                f"    - {lv.get('points')} pts: {lv.get('description')}"
                for lv in levels
            ]
        else:
            code = getattr(c, "code", "?")
            name = getattr(c, "name", code)
            max_pts = getattr(c, "max_points", 0)
            desc = getattr(c, "description", "")
            raw_levels = getattr(c, "scoring_levels", [])
            level_lines = []
            for lv in raw_levels:
                if isinstance(lv, dict):
                    level_lines.append(
                        f"    - {lv.get('points')} pts: {lv.get('description')}"
                    )
                else:
                    level_lines.append(
                        f"    - {getattr(lv, 'points', '?')} pts: "
                        f"{getattr(lv, 'description', '')}"
                    )
        blocks.append(
            f"Criterion `{code}` ({name}, max {max_pts}):\n"
            f"  Description: {desc}\n"
            f"  Official scoring levels:\n" + "\n".join(level_lines)
        )
    return "\n\n".join(blocks)


def _normalize_criteria(criteria: Sequence[Any]) -> list[dict[str, Any]]:
    """Return uniform dicts {code, name, max_points, scoring_levels, ...}."""
    out: list[dict[str, Any]] = []
    for c in criteria:
        if isinstance(c, dict):
            levels = c.get("scoring_levels", [])
            norm_levels = [
                {"points": lv.get("points", 0), "description": lv.get("description", "")}
                for lv in levels
            ]
            out.append(
                {
                    "code": c.get("code", "unknown"),
                    "name": c.get("name", c.get("code", "unknown")),
                    "description": c.get("description", ""),
                    "display_order": c.get("display_order", len(out) + 1),
                    "max_points": c.get("max_points", 0),
                    "scoring_levels": norm_levels,
                    "required_evidence_types": c.get("required_evidence_types", []),
                }
            )
        else:
            raw_levels = getattr(c, "scoring_levels", [])
            norm_levels = []
            for lv in raw_levels:
                if isinstance(lv, dict):
                    norm_levels.append(
                        {"points": lv.get("points", 0), "description": lv.get("description", "")}
                    )
                else:
                    norm_levels.append(
                        {"points": getattr(lv, "points", 0),
                         "description": getattr(lv, "description", "")}
                    )
            out.append(
                {
                    "code": getattr(c, "code", "unknown"),
                    "name": getattr(c, "name", getattr(c, "code", "unknown")),
                    "description": getattr(c, "description", ""),
                    "display_order": getattr(c, "display_order", len(out) + 1),
                    "max_points": getattr(c, "max_points", 0),
                    "scoring_levels": norm_levels,
                    "required_evidence_types": list(
                        getattr(c, "required_evidence_types", [])
                    ),
                }
            )
    return out


def _fallback_scored_criterion(
    criterion: dict[str, Any], evidence_text: str
) -> CriterionScoreProposal:
    """Deterministic rule-based scoring (offline/CI fallback).

    Conservative: awards 0 with needs_review unless keyword evidence matches;
    live-verification criteria always stay needs_review without reachable proof.
    """
    code = criterion["code"]
    max_points: int = int(criterion.get("max_points", 0) or 0)
    levels = criterion.get("scoring_levels", [])
    text = evidence_text.lower()
    keywords = _FALLBACK_KEYWORDS.get(code, [code.replace("_", " ")])
    hits = [kw for kw in keywords if kw.lower() in text]
    next_level_desc = None
    if levels and len(levels) > 1:
        next_level_desc = str(levels[1].get("description", ""))[:500]

    if code in _LIVE_VERIFICATION_CODES:
        return CriterionScoreProposal(
            criterion_code=code,
            ai_proposed_points=0,
            max_points=max_points,
            score_state=ScoreState.NEEDS_REVIEW,
            ai_confidence=0.35,
            ai_reasoning=(
                f"Offline fallback: no live runtime verification available for "
                f"`{code}`. "
                + (f"Keyword hints ({', '.join(hits)}) found in static evidence; "
                   if hits else "No deployment/telemetry evidence inspected; ")
                + "requires human review. " + ADVISORY_NOTICE
            ),
            missing_for_next_level=next_level_desc,
            cited_evidence_paths=[],
        )
    if hits:
        awarded = 1 if max_points >= 1 else 0
        # Never claim verified from keyword heuristics alone -> estimated.
        return CriterionScoreProposal(
            criterion_code=code,
            ai_proposed_points=min(awarded, max_points),
            max_points=max_points,
            score_state=ScoreState.ESTIMATED,
            ai_confidence=0.55,
            ai_reasoning=(
                f"Offline heuristic fallback: static evidence mentions "
                f"({', '.join(hits)}) relevant to `{code}`, but full official "
                f"scoring-level proof was not verified. " + ADVISORY_NOTICE
            ),
            missing_for_next_level=next_level_desc,
            cited_evidence_paths=[],
        )
    return CriterionScoreProposal(
        criterion_code=code,
        ai_proposed_points=0,
        max_points=max_points,
        score_state=ScoreState.NEEDS_REVIEW,
        ai_confidence=0.40,
        ai_reasoning=(
            f"Offline fallback: no evidence found for `{code}` in the inspected "
            f"bundle. " + ADVISORY_NOTICE
        ),
        missing_for_next_level=next_level_desc,
        cited_evidence_paths=[],
    )


def fallback_scorecard(
    criteria: Sequence[Any],
    evidence_items: Sequence[Any] | None = None,
    error: Exception | None = None,  # noqa: ARG001
) -> ScorecardEvaluationOutput:
    norm = _normalize_criteria(criteria)
    evidence_text = _evidence_to_bullets(evidence_items or [])
    proposals = [_fallback_scored_criterion(c, evidence_text) for c in norm]
    return ScorecardEvaluationOutput(
        criteria_evaluations=proposals,
        overall_assessment_summary=(
            "Deterministic offline fallback scorecard (Gemini unavailable). "
            "All scores are conservative AI estimates requiring human review. "
            + ADVISORY_NOTICE
        ),
    )


def evaluate_scorecard(
    criteria: Sequence[Any],
    evidence_items: Sequence[Any] | None = None,
    project_name: str = "",
    commit_sha: str | None = None,
) -> ScorecardEvaluationOutput:
    """Evaluate repo evidence against official scoring levels (Steps 1-4)."""
    norm = _normalize_criteria(criteria)
    evidence_block = _evidence_to_bullets(evidence_items or [])
    criteria_block = _criteria_to_prompt_block(criteria)

    def _prompt() -> tuple[str, str]:
        user = (
            f"Project: {project_name or '(unknown)'} | "
            f"commit_sha={commit_sha or 'unknown'}\n\n"
            f"OFFICIAL CRITERIA + SCORING LEVELS (evaluate strictly against these):\n"
            f"{criteria_block}\n\n"
            f"REPOSITORY EVIDENCE BUNDLE:\n{evidence_block}\n\n"
            "Return one evaluation per criterion with ai_proposed_points, "
            "ai_confidence, score_state, ai_reasoning citing concrete evidence "
            "paths/SHAs, cited_evidence_paths, and missing_for_next_level."
        )
        return (RUBRIC_ANALYST_SYSTEM, user)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=ScorecardEvaluationOutput,
        parse=lambda raw: ScorecardEvaluationOutput.model_validate(raw),
        fallback=lambda exc: fallback_scorecard(norm, evidence_items, exc),
    )


def fallback_extraction(
    raw_content: str,
    title: str = "Custom Course Rubric",
    course_name: str = "Custom Course",
    error: Exception | None = None,  # noqa: ARG001
) -> ExtractedRubricOutput:
    """Heuristic Markdown/text extraction fallback (never invents thresholds)."""
    text = raw_content or ""
    # Split on Markdown headings; each heading becomes a candidate criterion.
    headings = re.findall(r"^#{1,4}\s+(.+)$", text, flags=re.MULTILINE)
    items: list[ExtractedCriterionItem] = []
    order = 1
    for h in headings[:12]:
        code = re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_") or f"criterion_{order}"
        items.append(
            ExtractedCriterionItem(
                code=code[:64],
                name=h.strip()[:255],
                description=f"Extracted (offline fallback) from rubric source heading: {h.strip()}",
                display_order=order,
                max_points=2,
                scoring_levels=[
                    ScoringLevelItem(points=0, description="No evidence (fallback)."),
                    ScoringLevelItem(points=2, description=f"Evidence for {h.strip()} (fallback, needs review)."),
                ],
                required_evidence_types=[EvidenceType.DOCUMENTATION],
            )
        )
        order += 1
    if not items:
        items.append(
            ExtractedCriterionItem(
                code="general",
                name="General",
                description="Fallback single criterion: source had no parseable headings; needs human review.",
                display_order=1,
                max_points=2,
                scoring_levels=[
                    ScoringLevelItem(points=0, description="No evidence (fallback)."),
                    ScoringLevelItem(points=2, description="Evidence present (fallback, needs review)."),
                ],
                required_evidence_types=[EvidenceType.DOCUMENTATION],
            )
        )
    return ExtractedRubricOutput(
        title=title,
        course_name=course_name,
        max_points=sum(i.max_points for i in items),
        passing_threshold=None,
        criteria=items,
    )


def extract_rubric(
    raw_content: str,
    title: str = "Custom Course Rubric",
    course_name: str = "Custom Course",
    source_type: str = "text",
    source_url: str | None = None,
) -> ExtractedRubricOutput:
    """Ingest a custom rubric from URL/PDF/Markdown/text into structured criteria."""

    def _prompt() -> tuple[str, str]:
        # Cap raw content to keep prompts bounded; keep head where criteria live.
        clipped = (raw_content or "")[:12000]
        user = (
            f"Rubric title: {title}\nCourse: {course_name}\n"
            f"source_type={source_type} source_url={source_url or 'n/a'}\n\n"
            f"RAW RUBRIC CONTENT:\n{clipped}\n\n"
            "Extract title, course_name, max_points, passing_threshold (if stated), "
            "and every criterion with code, name, description, display_order, "
            "max_points, scoring_levels, required_evidence_types."
        )
        return (EXTRACTION_SYSTEM, user)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=ExtractedRubricOutput,
        parse=lambda raw: ExtractedRubricOutput.model_validate(raw),
        fallback=lambda exc: fallback_extraction(raw_content, title, course_name, exc),
    )


def scorecard_to_dicts(output: ScorecardEvaluationOutput) -> list[dict[str, Any]]:
    """Helper for Track 3 pipeline: ScorecardEvaluationOutput -> plain dicts."""
    return [item.model_dump() for item in output.criteria_evaluations]


def extraction_to_json(output: ExtractedRubricOutput) -> str:
    return json.dumps(output.model_dump(), indent=2)
