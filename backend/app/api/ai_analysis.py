from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_auth
from app.models.database import AsyncSessionLocal, get_db
from app.models.models import AIAnalysis
from app.models.models import Developer
from app.schemas.schemas import (
    AIAnalysisResponse,
    AIAnalyzeRequest,
    OneOnOnePrepRequest,
    TeamHealthRequest,
)
from app.services.ai_analysis import run_analysis, run_one_on_one_prep, run_team_health

router = APIRouter(dependencies=[Depends(require_auth)])


async def _run_analysis_background(request: AIAnalyzeRequest):
    """Run analysis in a background task with its own DB session."""
    async with AsyncSessionLocal() as db:
        await run_analysis(
            db=db,
            analysis_type=request.analysis_type.value,
            scope_type=request.scope_type.value,
            scope_id=request.scope_id,
            date_from=request.date_from,
            date_to=request.date_to,
        )


@router.post(
    "/ai/analyze",
    response_model=AIAnalysisResponse,
    status_code=201,
)
async def trigger_analysis(
    request: AIAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await run_analysis(
        db=db,
        analysis_type=request.analysis_type.value,
        scope_type=request.scope_type.value,
        scope_id=request.scope_id,
        date_from=request.date_from,
        date_to=request.date_to,
    )
    return result


@router.get("/ai/history", response_model=list[AIAnalysisResponse])
async def list_analyses(
    analysis_type: str | None = Query(None),
    scope_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AIAnalysis).order_by(AIAnalysis.created_at.desc())
    if analysis_type:
        stmt = stmt.where(AIAnalysis.analysis_type == analysis_type)
    if scope_type:
        stmt = stmt.where(AIAnalysis.scope_type == scope_type)
    result = await db.execute(stmt.limit(50))
    return result.scalars().all()


@router.get("/ai/history/{analysis_id}", response_model=AIAnalysisResponse)
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
):
    analysis = await db.get(AIAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.post(
    "/ai/one-on-one-prep",
    response_model=AIAnalysisResponse,
    status_code=201,
)
async def one_on_one_prep(
    request: OneOnOnePrepRequest,
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, request.developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return await run_one_on_one_prep(
        db=db,
        developer_id=request.developer_id,
        date_from=request.date_from,
        date_to=request.date_to,
    )


@router.post(
    "/ai/team-health",
    response_model=AIAnalysisResponse,
    status_code=201,
)
async def team_health(
    request: TeamHealthRequest,
    db: AsyncSession = Depends(get_db),
):
    return await run_team_health(
        db=db,
        team=request.team,
        date_from=request.date_from,
        date_to=request.date_to,
    )
