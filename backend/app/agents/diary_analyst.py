"""Diary Analyst runtime agent (Track 2).

Extracts completed work, blockers, architectural decisions, and next steps
from the developer's diary markdown/text, then cross-checks each claim
against recent Git history (commit messages + diff summary) to produce
``git_alignment_summary`` and explicit ``discrepancies``.
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

from app.schemas.agent_outputs import DiaryAnalysisOutput, DiaryDiscrepancyItem
from app.schemas.enums import SeverityLevel

DIARY_SYSTEM = (
    "You are DevTrack AI's Diary Analyst. Extract completed work, blockers, "
    "architectural decisions, and next steps from the developer's diary. Then "
    "cross-check every claim against the provided Git commit log and diff "
    "summary: confirm matches, and record mismatches as discrepancies with "
    "claim, git_reality, and severity (info/low/medium/high/critical). Be "
    "conservative — unverifiable claims become low-severity discrepancies, not "
    "confirmed work."
)


def _commits_to_text(commits: Sequence[Any], limit: int = 40) -> str:
    if not commits:
        return "(no commits provided)"
    lines = []
    for c in list(commits)[:limit]:
        if isinstance(c, dict):
            lines.append(
                f"- {c.get('sha', c.get('commit_sha', '?'))} "
                f"{c.get('date', '')} :: {c.get('message', c.get('title', ''))}".strip()
            )
        else:
            lines.append(f"- {c}")
    return "\n".join(lines)


def _fallback_section_parse(diary_text: str) -> dict[str, list[str]]:
    """Parse Markdown sections heuristically (offline fallback)."""
    sections = {"completed_work": [], "blockers": [], "decisions": [], "next_steps": []}
    # Bullets before any recognized heading default to completed work.
    current: str | None = "completed_work"
    mapping = {
        "complet": "completed_work", "done": "completed_work", "progress": "completed_work",
        "work": "completed_work", "block": "blockers", "stuck": "blockers",
        "issue": "blockers", "decis": "decisions", "decision": "decisions",
        "next": "next_steps", "todo": "next_steps", "plan": "next_steps",
    }
    for line in (diary_text or "").splitlines():
        h = re.match(r"^#{1,4}\s+(.+)$", line.strip())
        if h:
            title = h.group(1).lower()
            current = None
            for key, target in mapping.items():
                if key in title:
                    current = target
                    break
            continue
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet and current:
            sections[current].append(bullet.group(1).strip()[:300])
    # Fallback: treat any bullets as completed work if no sections matched.
    if not any(sections.values()):
        bullets = re.findall(r"^\s*[-*]\s+(.+)$", diary_text or "", flags=re.MULTILINE)
        sections["completed_work"] = [b.strip()[:300] for b in bullets[:10]]
    return sections


def fallback_diary_analysis(
    diary_text: str = "",
    commits: Sequence[Any] | None = None,
    discovered_path: str = "unknown",  # noqa: ARG001
    error: Exception | None = None,  # noqa: ARG001
) -> DiaryAnalysisOutput:
    sections = _fallback_section_parse(diary_text)
    commit_text = _commits_to_text(commits or []).lower()
    discrepancies: list[DiaryDiscrepancyItem] = []
    for claim in sections["completed_work"]:
        keywords = [w for w in re.findall(r"[a-z]{4,}", claim.lower())][:6]
        if keywords and not any(k in commit_text for k in keywords):
            discrepancies.append(
                DiaryDiscrepancyItem(
                    claim=claim,
                    git_reality=(
                        "Offline fallback: no matching commit message found for "
                        "this claim in the provided Git window; needs human review."
                    ),
                    severity=SeverityLevel.LOW,
                )
            )
    alignment = (
        "Offline deterministic fallback: diary sections parsed heuristically and "
        "keyword-matched against commit messages. "
        f"{len(sections['completed_work'])} work items, "
        f"{len(discrepancies)} unverified claims flagged. " + ADVISORY_NOTICE
    )
    return DiaryAnalysisOutput(
        completed_work=sections["completed_work"],
        blockers=sections["blockers"],
        decisions=sections["decisions"],
        next_steps=sections["next_steps"],
        git_alignment_summary=alignment,
        discrepancies=discrepancies,
    )


def analyze_diary(
    diary_text: str,
    commits: Sequence[Any] | None = None,
    diff_summary: str = "",
    discovered_path: str = "unknown",
) -> DiaryAnalysisOutput:
    """Extract diary structure and cross-check vs Git history."""

    def _prompt() -> tuple[str, str]:
        clipped = (diary_text or "")[:12000]
        user = (
            f"Diary path: {discovered_path}\n\n"
            f"DIARY CONTENT:\n{clipped or '(empty diary)'}\n\n"
            f"GIT COMMIT LOG:\n{_commits_to_text(commits or [])}\n\n"
            f"DIFF SUMMARY:\n{(diff_summary or '(none)')[:4000]}\n\n"
            "Extract completed_work, blockers, decisions, next_steps; write "
            "git_alignment_summary; list discrepancies (claim/git_reality/severity)."
        )
        return (DIARY_SYSTEM, user)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=DiaryAnalysisOutput,
        parse=lambda raw: DiaryAnalysisOutput.model_validate(raw),
        fallback=lambda exc: fallback_diary_analysis(
            diary_text, commits, discovered_path, exc
        ),
    )
