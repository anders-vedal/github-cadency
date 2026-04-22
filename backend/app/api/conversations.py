"""Phase 04 — Issue Conversations API."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.models.database import get_db
from app.schemas.schemas import (
    AuthUser,
    ChattyIssueRow,
    ConversationsScatterPoint,
    FirstResponseHistogramBucket,
    ParticipantDistributionBucket,
)
from app.services.issue_conversations import (
    get_chattiest_issues,
    get_comment_vs_bounce_scatter,
    get_first_response_histogram,
    get_participant_distribution,
)

router = APIRouter()


@router.get("/conversations/chattiest", response_model=list[ChattyIssueRow])
async def chattiest_issues(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    project_id: int | None = Query(None),
    creator_id: int | None = Query(None),
    assignee_id: int | None = Query(None),
    label: str | None = Query(None),
    priority: int | None = Query(None),
    has_linked_pr: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    rows = await get_chattiest_issues(
        db,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        project_id=project_id,
        creator_id=creator_id,
        assignee_id=assignee_id,
        label=label,
        priority=priority,
        has_linked_pr=has_linked_pr,
    )
    return rows


@router.get("/conversations/scatter", response_model=list[ConversationsScatterPoint])
async def comment_bounce_scatter(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_comment_vs_bounce_scatter(db, date_from=date_from, date_to=date_to)


@router.get("/conversations/first-response", response_model=list[FirstResponseHistogramBucket])
async def first_response(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_first_response_histogram(db, date_from=date_from, date_to=date_to)


@router.get("/conversations/participants", response_model=list[ParticipantDistributionBucket])
async def participants(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_participant_distribution(db, date_from=date_from, date_to=date_to)
