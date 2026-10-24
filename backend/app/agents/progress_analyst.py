"""Progress Analyst runtime agent (Track 2).

Two strictly separate dimensions (never conflated):

- **Development Completion**: actionable task progress (completed / partial /
  outstanding), deadline adherence, stalled/scope-creep flags. Completing dev
  tasks MUST NOT auto-award official assessment points.
- **Expected Course Score**: handled by the Rubric Analyst / scorecard; this
  agent never assigns criterion points.

Outputs: ``ProgressEvaluationOutput`` (evaluation) and
``MilestonePlanGenerationOutput`` (draft dev-task planning).
"""

from __future__ import annotations

from typing import Any, Sequence

from app.agents.base import ADVISORY_NOTICE, run_with_fallback

from app.schemas.agent_outputs import (
    GeneratedDevTaskItem,
    MilestonePlanGenerationOutput,
    ProgressEvaluationOutput,
)

PROGRESS_SYSTEM = (
    "You are DevTrack AI's Progress Analyst. Evaluate DEVELOPMENT COMPLETION "
    "only: which development tasks are completed/partial/outstanding, deadline "
    "adherence, and whether work is stalled or scope-creeping versus the "
    "previous commit SHA. NEVER award official course rubric points — that is "
    "the Rubric Analyst's job. Development Completion and Expected Course "
    "Score are separate dimensions. Cite commit SHAs and file paths."
)

PLAN_SYSTEM = (
    "You are DevTrack AI's Progress Analyst (planning mode). Draft actionable "
    "development tasks linked to assessment criterion codes. Tasks must be "
    "concrete, small (0.5h+), and must NOT claim to award rubric points on "
    "completion."
)


def _tasks_to_text(tasks: Sequence[Any]) -> str:
    if not tasks:
        return "(no development tasks)"
    lines = []
    for t in tasks:
        if isinstance(t, dict):
            lines.append(
                f"- {t.get('title', '?')} [status={t.get('status', '?')}] "
                f"(criterion={t.get('criterion_code', t.get('assessment_milestone_id', '?'))})"
            )
        else:
            lines.append(
                f"- {getattr(t, 'title', '?')} [status={getattr(t, 'status', '?')}]"
            )
    return "\n".join(lines)


def _commits_to_text(commits: Sequence[Any], limit: int = 30) -> str:
    if not commits:
        return "(no commits in window)"
    lines = []
    for c in list(commits)[:limit]:
        if isinstance(c, dict):
            lines.append(
                f"- {c.get('sha', c.get('commit_sha', '?'))[:12]} "
                f"{c.get('date', '')} {c.get('message', c.get('title', ''))}".strip()
            )
        else:
            lines.append(f"- {getattr(c, 'sha', getattr(c, 'commit_sha', '?'))} {c}")
    return "\n".join(lines)


def fallback_progress(
    dev_tasks: Sequence[Any] | None = None,
    error: Exception | None = None,  # noqa: ARG001
) -> ProgressEvaluationOutput:
    """Deterministic offline evaluation from task statuses (no points awarded)."""
    completed, partial, outstanding = [], [], []
    for t in dev_tasks or []:
        if isinstance(t, dict):
            title = str(t.get("title", "untitled"))
            status = str(t.get("status", "outstanding")).lower()
        else:
            title = str(getattr(t, "title", "untitled"))
            status = str(getattr(t, "status", "outstanding")).lower()
        if status == "completed":
            completed.append(title)
        elif status == "partial":
            partial.append(title)
        else:
            outstanding.append(title)
    total = len(completed) + len(partial) + len(outstanding)
    pct = (len(completed) / total * 100.0) if total else 0.0
    return ProgressEvaluationOutput(
        completed_task_titles=completed,
        partial_task_titles=partial,
        outstanding_task_titles=outstanding,
        dev_completion_pct=round(pct, 1),
        deadline_adherence_summary=(
            "Offline fallback: deadline adherence could not be verified without "
            "live schedule context; task counts derived deterministically. "
            + ADVISORY_NOTICE
        ),
        stalled_development_detected=False,
        scope_creep_detected=False,
    )


def evaluate_progress(
    dev_tasks: Sequence[Any] | None = None,
    commits: Sequence[Any] | None = None,
    previous_commit_sha: str | None = None,
    current_commit_sha: str | None = None,
    changed_files: Sequence[str] | None = None,
) -> ProgressEvaluationOutput:
    """Evaluate Development Completion separately from Expected Course Score."""

    def _prompt() -> tuple[str, str]:
        user = (
            f"previous_commit_sha={previous_commit_sha or 'none'} "
            f"current_commit_sha={current_commit_sha or 'unknown'}\n"
            f"Changed files since previous SHA:\n"
            f"{', '.join(changed_files or []) or '(none reported)'}\n\n"
            f"DEVELOPMENT TASKS:\n{_tasks_to_text(dev_tasks or [])}\n\n"
            f"COMMIT HISTORY (window):\n{_commits_to_text(commits or [])}\n\n"
            "Classify each development task as completed/partial/outstanding, "
            "compute dev_completion_pct, summarize deadline adherence, and flag "
            "stalled development or scope creep vs the previous SHA. "
            "Do NOT assign rubric points."
        )
        return (PROGRESS_SYSTEM, user)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=ProgressEvaluationOutput,
        parse=lambda raw: ProgressEvaluationOutput.model_validate(raw),
        fallback=lambda exc: fallback_progress(dev_tasks, exc),
    )


def fallback_plan(
    assessment_criteria: Sequence[Any] | None = None,
    error: Exception | None = None,  # noqa: ARG001
) -> MilestonePlanGenerationOutput:
    """Offline plan: one generic dev task per criterion (no points awarded)."""
    tasks = []
    for c in assessment_criteria or []:
        if isinstance(c, dict):
            code = str(c.get("code", "general"))
            name = str(c.get("name", code))
        else:
            code = str(getattr(c, "code", "general"))
            name = str(getattr(c, "name", code))
        tasks.append(
            GeneratedDevTaskItem(
                criterion_code=code,
                title=f"Implement evidence for {name}",
                description=(
                    f"Offline fallback task: collect concrete evidence for `{code}` "
                    f"(docs/code/config). Completing this task does not award "
                    f"official points."
                ),
                estimated_effort_hours=2.0,
            )
        )
    if not tasks:
        try:
            tasks.append(
                GeneratedDevTaskItem(
                    criterion_code="general",
                    title="Establish baseline project structure",
                    description=(
                        "Offline fallback: create README, spec, and task breakdown. "
                        "Completing this task does not award official points."
                    ),
                    estimated_effort_hours=2.0,
                )
            )
        except Exception:
            pass
    return MilestonePlanGenerationOutput(development_tasks=tasks)


def generate_milestone_plan(
    assessment_criteria: Sequence[Any] | None = None,
    project_description: str = "",
) -> MilestonePlanGenerationOutput:
    """Draft development tasks linked to assessment criteria (advisory only)."""

    def _prompt() -> tuple[str, str]:
        codes = []
        for c in assessment_criteria or []:
            if isinstance(c, dict):
                codes.append(f"- {c.get('code')}: {c.get('name', '')}")
            else:
                codes.append(f"- {getattr(c, 'code', '?')}: {getattr(c, 'name', '')}")
        user = (
            f"Project: {project_description or '(no description)'}\n"
            f"Assessment criteria:\n" + ("\n".join(codes) or "(none)") + "\n\n"
            "Draft 1-3 concrete development tasks per criterion with titles, "
            "descriptions, and effort hours. Link each via criterion_code."
        )
        return (PLAN_SYSTEM, user)

    return run_with_fallback(
        prompt_builder=_prompt,
        response_schema=MilestonePlanGenerationOutput,
        parse=lambda raw: MilestonePlanGenerationOutput.model_validate(raw),
        fallback=lambda exc: fallback_plan(assessment_criteria, exc),
    )
