"""Phase 06 — Flow analytics API."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.models.database import get_db
from app.schemas.schemas import (
    AuthUser,
    FlowReadinessResponse,
    RefinementChurnResponse,
    StatusRegression,
    StatusTimeDistribution,
    TriageBounce,
)
from app.services.flow_analytics import (
    get_refinement_churn,
    get_status_regressions,
    get_status_time_distribution,
    get_triage_bounces,
    has_sufficient_history,
)

router = APIRouter()


@router.get("/flow/readiness", response_model=FlowReadinessResponse)
async def flow_readiness(
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await has_sufficient_history(db)


@router.get("/flow/status-distribution", response_model=list[StatusTimeDistribution])
async def status_distribution(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    group_by: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_status_time_distribution(
        db, date_from=date_from, date_to=date_to, group_by=group_by
    )


@router.get("/flow/regressions", response_model=list[StatusRegression])
async def status_regressions(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_status_regressions(db, date_from=date_from, date_to=date_to)


@router.get("/flow/triage-bounces", response_model=list[TriageBounce])
async def triage_bounces(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_triage_bounces(db, date_from=date_from, date_to=date_to)


@router.get("/flow/refinement-churn", response_model=RefinementChurnResponse)
async def refinement_churn(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_refinement_churn(db, date_from=date_from, date_to=date_to)
