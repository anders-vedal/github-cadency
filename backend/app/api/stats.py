from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.models.database import get_db
from app.models.models import Developer, Repository
from app.schemas.schemas import (
    BenchmarksResponse,
    CollaborationResponse,
    DeveloperStatsResponse,
    DeveloperStatsWithPercentilesResponse,
    DeveloperTrendsResponse,
    RepoStatsResponse,
    TeamStatsResponse,
    WorkloadResponse,
)
from app.services.collaboration import get_collaboration
from app.services.stats import (
    get_benchmarks,
    get_developer_stats,
    get_developer_stats_with_percentiles,
    get_developer_trends,
    get_repo_stats,
    get_team_stats,
    get_workload,
)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get(
    "/stats/developer/{developer_id}",
    response_model=DeveloperStatsResponse | DeveloperStatsWithPercentilesResponse,
)
async def developer_stats(
    developer_id: int,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    include_percentiles: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    if include_percentiles:
        return await get_developer_stats_with_percentiles(
            db, developer_id, date_from, date_to
        )
    return await get_developer_stats(db, developer_id, date_from, date_to)


@router.get("/stats/team", response_model=TeamStatsResponse)
async def team_stats(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await get_team_stats(db, team, date_from, date_to)


@router.get("/stats/repo/{repo_id}", response_model=RepoStatsResponse)
async def repo_stats(
    repo_id: int,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    repo = await db.get(Repository, repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return await get_repo_stats(db, repo_id, date_from, date_to)


@router.get("/stats/benchmarks", response_model=BenchmarksResponse)
async def benchmarks(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await get_benchmarks(db, team, date_from, date_to)


@router.get(
    "/stats/developer/{developer_id}/trends",
    response_model=DeveloperTrendsResponse,
)
async def developer_trends(
    developer_id: int,
    periods: int = Query(8, ge=2, le=52),
    period_type: str = Query("week"),
    sprint_length_days: int = Query(14, ge=7, le=28),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return await get_developer_trends(
        db, developer_id, periods, period_type, sprint_length_days
    )


@router.get("/stats/collaboration", response_model=CollaborationResponse)
async def collaboration(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await get_collaboration(db, team, date_from, date_to)


@router.get("/stats/workload", response_model=WorkloadResponse)
async def workload(
    team: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await get_workload(db, team, date_from, date_to)
