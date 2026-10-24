"""Rubric endpoints: list / detail / ingest stub.

Ingest is a Track 1 stub: it persists a NEW versioned rubric row (never
overwrites in place) from the request payload. Track 2's Rubric Analyst
(RubricAnalystProtocol) will fill criteria via LLM extraction; until wired,
criteria provided inline in raw_content are not parsed — pass an empty list
and let Track 2 enrich the version.
"""

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.db.init_db import seed_builtin_rubric
from app.models.models import Rubric, RubricCriterion
from app.schemas.api_contracts import (
    RubricCriterionSchema,
    RubricDetailSchema,
    RubricIngestRequest,
    RubricSummarySchema,
    UserProfileSchema,
)
from app.schemas.enums import RubricSourceType

router = APIRouter(prefix="/rubrics", tags=["rubrics"])


def _to_summary(r: Rubric) -> RubricSummarySchema:
    return RubricSummarySchema(
        id=r.id,
        slug=r.slug,
        title=r.title,
        course_name=r.course_name,
        source_type=r.source_type,
        source_url=r.source_url,
        version=r.version,
        retrieved_at=r.retrieved_at,
        is_official=r.is_official,
        max_points=r.max_points,
        passing_threshold=r.passing_threshold,
    )


def _to_detail(r: Rubric, criteria: list[RubricCriterion]) -> RubricDetailSchema:
    return RubricDetailSchema(
        **_to_summary(r).model_dump(),
        raw_content=r.raw_content,
        criteria=[
            RubricCriterionSchema(
                id=c.id,
                code=c.code,
                name=c.name,
                description=c.description,
                display_order=c.display_order,
                max_points=c.max_points,
                scoring_levels=c.scoring_levels,
                required_evidence_types=c.required_evidence_types,
            )
            for c in sorted(criteria, key=lambda x: x.display_order)
        ],
    )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:100] or "custom-rubric"


@router.get("", response_model=list[RubricSummarySchema])
def list_rubrics(
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> list[RubricSummarySchema]:
    seed_builtin_rubric(db)  # guarantee the built-in rubric is always listed
    rubrics = db.query(Rubric).order_by(Rubric.created_at).all()
    return [_to_summary(r) for r in rubrics]


@router.get("/{rubric_id}", response_model=RubricDetailSchema)
def get_rubric(
    rubric_id: UUID,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> RubricDetailSchema:
    rubric = db.get(Rubric, rubric_id)
    if rubric is None:
        raise HTTPException(status_code=404, detail="Rubric not found")
    criteria = (
        db.query(RubricCriterion)
        .filter(RubricCriterion.rubric_id == rubric.id)
        .order_by(RubricCriterion.display_order)
        .all()
    )
    return _to_detail(rubric, criteria)


@router.post("/ingest", response_model=RubricDetailSchema, status_code=201)
def ingest_rubric(
    body: RubricIngestRequest,
    db: Session = Depends(get_db),
    _user: UserProfileSchema = Depends(get_current_user),
) -> RubricDetailSchema:
    # Track 2 hook: RubricAnalystProtocol.extract_rubric() will replace this
    # stub parsing once wired. We persist a new versioned row regardless.
    if body.source_type == RubricSourceType.URL and not body.source_url:
        raise HTTPException(
            status_code=400, detail="source_url is required for url rubrics"
        )
    rubric = Rubric(
        slug=f"{_slugify(body.title)}-{body.version}",
        title=body.title,
        course_name=body.course_name,
        source_type=body.source_type,
        source_url=body.source_url,
        raw_content=body.raw_content,
        version=body.version,
        is_official=False,
        max_points=0,
        passing_threshold=None,
    )
    db.add(rubric)
    db.commit()
    db.refresh(rubric)
    return _to_detail(rubric, [])
