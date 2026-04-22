"""Phase 07 — Bottleneck intelligence API."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.models.database import get_db
from app.schemas.schemas import (
    AuthUser,
    BlockedChainRow,
    BottleneckDigestItem,
    BusFactorFileRow,
    CrossTeamHandoff,
    CumulativeFlowPoint,
    CycleTimeHistogramResponse,
    ReviewLoadGini,
    ReviewNetworkResponse,
    ReviewPingPongRow,
    WipOverLimit,
)
from app.services.bottleneck_intelligence import (
    get_blocked_chains,
    get_bottleneck_summary,
    get_bus_factor_by_file,
    get_cross_team_handoffs,
    get_cumulative_flow,
    get_cycle_time_histogram,
    get_review_load_gini,
    get_review_network,
    get_review_ping_pong,
    get_wip_per_developer,
)

router = APIRouter()


@router.get("/bottlenecks/cumulative-flow", response_model=list[CumulativeFlowPoint])
async def cumulative_flow(
    cycle_id: int | None = Query(None),
    project_id: int | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_cumulative_flow(
        db,
        cycle_id=cycle_id,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/bottlenecks/wip", response_model=list[WipOverLimit])
async def wip(
    threshold: int = Query(4, ge=1),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_wip_per_developer(db, limit=threshold)


@router.get("/bottlenecks/review-load", response_model=ReviewLoadGini)
async def review_load(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_review_load_gini(db, date_from=date_from, date_to=date_to)


@router.get("/bottlenecks/review-network", response_model=ReviewNetworkResponse)
async def review_network(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_review_network(db, date_from=date_from, date_to=date_to)


@router.get("/bottlenecks/cross-team-handoffs", response_model=list[CrossTeamHandoff])
async def cross_team_handoffs(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_cross_team_handoffs(db, date_from=date_from, date_to=date_to)


@router.get("/bottlenecks/blocked-chains", response_model=list[BlockedChainRow])
async def blocked_chains(
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_blocked_chains(db)


@router.get("/bottlenecks/ping-pong", response_model=list[ReviewPingPongRow])
async def review_ping_pong(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_review_ping_pong(db, date_from=date_from, date_to=date_to)


@router.get("/bottlenecks/bus-factor-files", response_model=list[BusFactorFileRow])
async def bus_factor_files(
    since_days: int = Query(90, ge=7),
    min_authors: int = Query(2, ge=1),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_bus_factor_by_file(
        db, since_days=since_days, min_authors=min_authors
    )


@router.get("/bottlenecks/cycle-histogram", response_model=CycleTimeHistogramResponse)
async def cycle_histogram(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_cycle_time_histogram(db, date_from=date_from, date_to=date_to)


@router.get("/bottlenecks/summary", response_model=list[BottleneckDigestItem])
async def summary(
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    return await get_bottleneck_summary(db)
