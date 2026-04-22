"""Phase 03 — Linear Usage Health API."""

from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.models.database import get_db
from app.models.models import ExternalIssue
from app.schemas.schemas import AuthUser, LinearUsageHealthResponse
from app.services.linear_health import get_linear_usage_health, is_linear_primary

router = APIRouter()


@router.get("/linear/usage-health", response_model=LinearUsageHealthResponse)
async def linear_usage_health(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Return the five Linear usage-health signals. Requires Linear as primary issue source."""
    if not await is_linear_primary(db):
        raise HTTPException(
            status_code=409,
            detail="Linear is not configured as the primary issue source.",
        )
    data = await get_linear_usage_health(db, date_from=date_from, date_to=date_to)
    return LinearUsageHealthResponse(**data)


@router.get("/linear/labels")
async def linear_labels(
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Return distinct Linear labels in use, ordered by issue frequency.

    Powers the Conversations page label picker. Returns up to 200 labels —
    workspaces with more than that need server-side typeahead, which is a
    future enhancement. Counts are issue-count, not comment-count.
    """
    if not await is_linear_primary(db):
        raise HTTPException(
            status_code=409,
            detail="Linear is not configured as the primary issue source.",
        )
    # `labels` is a JSONB list of label-name strings per issue. SQL-side
    # jsonb_array_elements_text would be nicer on Postgres but SQLite (tests)
    # doesn't support it, so flatten in Python. Reasonable for 10k-issue
    # workspaces because we only scan the list column.
    rows = (
        await db.execute(
            select(ExternalIssue.labels).where(ExternalIssue.labels.isnot(None))
        )
    ).all()
    counter: Counter[str] = Counter()
    for (labels,) in rows:
        if not labels:
            continue
        for lbl in labels:
            if isinstance(lbl, str) and lbl:
                counter[lbl] += 1
    top = counter.most_common(200)
    return {
        "labels": [{"name": name, "count": count} for name, count in top],
    }
