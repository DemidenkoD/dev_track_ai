"""Versioned rubric loading / validation / mapping helpers (Track 2).

Pure logic only: no API routes, no DB engine/session creation. Callers
(Track 1 API, Track 3 worker) pass in sessions or ORM objects; this module
only transforms data and delegates LLM ingestion to
``backend/app/agents/rubric_analyst.py``.

Follows ``.agents/skills/rubric-evaluation/SKILL.md``:
- Step 1: scoring levels always load from the versioned official JSON or DB.
- Step 5: helpers never overwrite human overrides (mapping preserves
  ``ai_proposed_points``/``ai_reasoning`` fields separately).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

try:
    from app.agents.base import ADVISORY_NOTICE  # noqa: F401 (path bootstrap)
except ImportError:  # harness imports as backend.app.*: fix sys.path first
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

from app.schemas.agent_outputs import ExtractedRubricOutput

OFFICIAL_RUBRIC_SLUG = "ai-dev-tools-zoomcamp-2026"
OFFICIAL_RUBRIC_VERSION = "2026.1.0"
OFFICIAL_MAX_POINTS = 24
OFFICIAL_PASSING_THRESHOLD = 10
OFFICIAL_CRITERION_COUNT = 12


def official_rubric_path(explicit: str | Path | None = None) -> Path:
    """Resolve the official rubric JSON path (explicit > repo-relative)."""
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve()
    # backend/app/services/rubric_service.py -> repo root is 4 levels up.
    for candidate in [
        here.parents[3] / "docs" / "rubrics" / "ai_dev_tools_zoomcamp_2026.json",
        Path.cwd() / "docs" / "rubrics" / "ai_dev_tools_zoomcamp_2026.json",
        Path.cwd() / "backend" / ".." / "docs" / "rubrics" / "ai_dev_tools_zoomcamp_2026.json",
    ]:
        if candidate.exists():
            return candidate
    return here.parents[3] / "docs" / "rubrics" / "ai_dev_tools_zoomcamp_2026.json"


def load_official_rubric(path: str | Path | None = None) -> dict[str, Any]:
    """Load the versioned official rubric JSON (Step 1 of the skill)."""
    resolved = official_rubric_path(path)
    with open(resolved, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Rubric file {resolved} must contain a JSON object.")
    return data


def validate_rubric_dict(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a rubric dict; return (is_valid, errors). Never mutates input."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return False, ["rubric payload must be a JSON object"]
    for field in ("title", "course_name", "criteria"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    criteria = data.get("criteria", [])
    if not isinstance(criteria, list) or not criteria:
        errors.append("criteria must be a non-empty list")
        return False, errors
    codes: set[str] = set()
    total = 0
    for i, c in enumerate(criteria):
        prefix = f"criteria[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{prefix} must be an object")
            continue
        for field in ("code", "name", "max_points", "scoring_levels"):
            if field not in c:
                errors.append(f"{prefix} missing field: {field}")
        code = c.get("code", "")
        if code in codes:
            errors.append(f"{prefix} duplicate code: {code!r}")
        codes.add(code)
        max_pts = c.get("max_points", 0)
        if not isinstance(max_pts, int) or max_pts < 1:
            errors.append(f"{prefix} max_points must be a positive int")
        else:
            total += max_pts
        levels = c.get("scoring_levels", [])
        if not isinstance(levels, list) or not levels:
            errors.append(f"{prefix} scoring_levels must be a non-empty list")
            continue
        points_seen = set()
        for lv in levels:
            if not isinstance(lv, dict) or "points" not in lv or "description" not in lv:
                errors.append(f"{prefix} scoring level must have points + description")
                continue
            p = lv["points"]
            if not isinstance(p, int) or p < 0 or p > max_pts:
                errors.append(f"{prefix} level points {p!r} out of range 0..{max_pts}")
            points_seen.add(p)
        if max_pts not in points_seen:
            errors.append(f"{prefix} scoring_levels must include max_points={max_pts}")
    declared_max = data.get("max_points")
    if isinstance(declared_max, int) and declared_max != total:
        errors.append(
            f"max_points={declared_max} inconsistent with criteria sum={total}"
        )
    return (len(errors) == 0), errors


def validate_official_rubric(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate the built-in 2026 rubric invariants (12 criteria / 24 pts / 10)."""
    valid, errors = validate_rubric_dict(data)
    errors = list(errors)
    criteria = data.get("criteria", []) if isinstance(data, dict) else []
    if len(criteria) != OFFICIAL_CRITERION_COUNT:
        errors.append(
            f"official rubric must have {OFFICIAL_CRITERION_COUNT} criteria, "
            f"found {len(criteria)}"
        )
    total = sum(
        c.get("max_points", 0) for c in criteria if isinstance(c, dict)
    )
    if total != OFFICIAL_MAX_POINTS:
        errors.append(
            f"official rubric must total {OFFICIAL_MAX_POINTS} points, found {total}"
        )
    if data.get("passing_threshold") != OFFICIAL_PASSING_THRESHOLD:
        errors.append(
            f"official passing_threshold must be {OFFICIAL_PASSING_THRESHOLD}, "
            f"found {data.get('passing_threshold')!r}"
        )
    return (len(errors) == 0), errors


def rubric_dict_to_extracted_output(data: dict[str, Any]) -> ExtractedRubricOutput:
    """Convert a validated rubric dict to ExtractedRubricOutput-compatible model."""
    return ExtractedRubricOutput.model_validate(
        {
            "title": data.get("title", ""),
            "course_name": data.get("course_name", ""),
            "max_points": data.get(
                "max_points",
                sum(c.get("max_points", 0) for c in data.get("criteria", [])),
            ),
            "passing_threshold": data.get("passing_threshold"),
            "criteria": [
                {
                    "code": c.get("code", ""),
                    "name": c.get("name", ""),
                    "description": c.get("description", ""),
                    "display_order": c.get("display_order", i + 1),
                    "max_points": c.get("max_points", 0),
                    "scoring_levels": c.get("scoring_levels", []),
                    "required_evidence_types": c.get("required_evidence_types", []),
                }
                for i, c in enumerate(data.get("criteria", []))
            ],
        }
    )


def map_db_criteria_to_evaluation_input(
    db_criteria: Sequence[Any],
) -> list[dict[str, Any]]:
    """Map DB ``RubricCriterion`` rows (or ORM-like objects) to evaluator input.

    Accepts SQLAlchemy objects, Pydantic models, or plain dicts; returns plain
    dicts with code/name/description/display_order/max_points/scoring_levels/
    required_evidence_types. Never touches the DB itself.
    """
    out: list[dict[str, Any]] = []
    for c in db_criteria:
        if isinstance(c, dict):
            levels = c.get("scoring_levels", [])
            norm_levels = [
                {"points": lv.get("points", 0), "description": lv.get("description", "")}
                if isinstance(lv, dict)
                else {"points": getattr(lv, "points", 0),
                      "description": getattr(lv, "description", "")}
                for lv in levels
            ]
            out.append(
                {
                    "code": c.get("code", ""),
                    "name": c.get("name", ""),
                    "description": c.get("description", ""),
                    "display_order": c.get("display_order", len(out) + 1),
                    "max_points": c.get("max_points", 0),
                    "scoring_levels": norm_levels,
                    "required_evidence_types": list(c.get("required_evidence_types", [])),
                }
            )
            continue
        raw_levels = getattr(c, "scoring_levels", [])
        norm_levels = []
        for lv in raw_levels or []:
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
                "code": getattr(c, "code", ""),
                "name": getattr(c, "name", ""),
                "description": getattr(c, "description", ""),
                "display_order": getattr(c, "display_order", len(out) + 1),
                "max_points": getattr(c, "max_points", 0),
                "scoring_levels": norm_levels,
                "required_evidence_types": list(
                    getattr(c, "required_evidence_types", []) or []
                ),
            }
        )
    out.sort(key=lambda d: d.get("display_order", 0))
    return out


def build_seed_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Build Track 1-friendly seed payload (rubric row + criterion rows).

    Returns plain dicts only — the caller performs the actual INSERT so this
    module never creates a DB engine/session.
    """
    valid, errors = validate_rubric_dict(data)
    if not valid:
        raise ValueError(f"Invalid rubric dict: {errors}")
    return {
        "rubric": {
            "slug": data.get("rubric_id", OFFICIAL_RUBRIC_SLUG),
            "title": data["title"],
            "course_name": data["course_name"],
            "source_type": "builtin",
            "source_url": data.get("source_url"),
            "raw_content": json.dumps(data)[:20000],
            "version": data.get("version", OFFICIAL_RUBRIC_VERSION),
            "is_official": bool(data.get("is_official", True)),
            "max_points": data.get("max_points", OFFICIAL_MAX_POINTS),
            "passing_threshold": data.get("passing_threshold"),
        },
        "criteria": map_db_criteria_to_evaluation_input(data.get("criteria", [])),
    }


def get_criterion_by_code(
    criteria: Sequence[dict[str, Any]], code: str
) -> dict[str, Any] | None:
    for c in criteria:
        if c.get("code") == code:
            return c
    return None


def compute_totals(criteria: Sequence[dict[str, Any]]) -> dict[str, int | None]:
    total = sum(int(c.get("max_points", 0) or 0) for c in criteria)
    return {"max_points": total, "criterion_count": len(criteria)}


def build_evidence_bundle(evidence_items: Sequence[Any]) -> list[dict[str, Any]]:
    """Normalize evidence rows/objects to plain dicts for agent prompts."""
    bundle: list[dict[str, Any]] = []
    for ev in evidence_items:
        if isinstance(ev, dict):
            bundle.append(
                {
                    "evidence_type": str(ev.get("evidence_type", "unknown")),
                    "title": str(ev.get("title", "")),
                    "path_or_url": str(ev.get("path_or_url", "")),
                    "commit_sha": ev.get("commit_sha"),
                    "snippet": str(ev.get("snippet", "") or "")[:2000],
                    "metadata": ev.get("metadata_json", ev.get("metadata", {})),
                }
            )
        else:
            bundle.append(
                {
                    "evidence_type": str(getattr(ev, "evidence_type", "unknown")),
                    "title": str(getattr(ev, "title", "")),
                    "path_or_url": str(getattr(ev, "path_or_url", "")),
                    "commit_sha": getattr(ev, "commit_sha", None),
                    "snippet": str(getattr(ev, "snippet", "") or "")[:2000],
                    "metadata": getattr(ev, "metadata_json", {}),
                }
            )
    return bundle


def ingest_raw_content(
    raw_content: str,
    title: str = "Custom Course Rubric",
    course_name: str = "Custom Course",
    source_type: str = "text",
    source_url: str | None = None,
) -> dict[str, Any]:
    """Ingest raw rubric text via RubricAnalyst; return ExtractedRubricOutput dict.

    Uses the deterministic fallback automatically when Gemini is unavailable,
    so seeding/ingestion never crashes CI.
    """
    from app.agents.rubric_analyst import extract_rubric
    output = extract_rubric(
        raw_content,
        title=title,
        course_name=course_name,
        source_type=source_type,
        source_url=source_url,
    )
    return output.model_dump()


def merge_human_override(
    ai_record: dict[str, Any], human_override_points: int | None, reason: str | None = None
) -> dict[str, Any]:
    """Return a scorecard record preserving AI fields alongside human override.

    Step 5 of the skill: never overwrite ``ai_proposed_points`` /
    ``ai_reasoning`` — the override lives in separate keys with an
    ``effective_points`` convenience value.
    """
    merged = dict(ai_record)
    merged["human_override_points"] = human_override_points
    merged["human_override_reason"] = reason
    if human_override_points is not None:
        merged["effective_points"] = human_override_points
    else:
        merged["effective_points"] = merged.get("ai_proposed_points", 0)
    return merged
