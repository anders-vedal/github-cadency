from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.models.database import get_db
from app.models.models import AIAnalysis, Developer
from app.schemas.schemas import (
    AICostEstimate,
    AIAnalysisResponse,
    AIAnalyzeRequest,
    AIScheduleCreate,
    AIScheduleResponse,
    AIScheduleUpdate,
    AISettingsResponse,
    AISettingsUpdate,
    AIUsageSummary,
    AuthUser,
    OneOnOnePrepRequest,
    TeamHealthRequest,
)
from app.services.ai_analysis import run_analysis, run_one_on_one_prep, run_team_health
from app.services.ai_schedules import (
    compute_next_run_description,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    run_scheduled_analysis,
    update_schedule,
)
from app.services.exceptions import AIBudgetExceededError, AIFeatureDisabledError
from app.services.ai_settings import (
    build_settings_response,
    estimate_analysis_cost,
    get_ai_settings,
    get_usage_summary,
    update_ai_settings,
)

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/ai/settings", response_model=AISettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Get current AI settings with usage summary."""
    ai_settings = await get_ai_settings(db)
    data = await build_settings_response(db, ai_settings)
    return AISettingsResponse(**data)


@router.patch("/ai/settings", response_model=AISettingsResponse)
async def patch_settings(
    updates: AISettingsUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Update AI settings (admin only)."""
    ai_settings = await update_ai_settings(db, updates, updated_by=user.github_username)
    data = await build_settings_response(db, ai_settings)
    return AISettingsResponse(**data)


@router.get("/ai/usage", response_model=AIUsageSummary)
async def get_usage(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Usage breakdown by feature with daily timeseries."""
    ai_settings = await get_ai_settings(db)
    return await get_usage_summary(db, ai_settings, days=days)


@router.post("/ai/estimate", response_model=AICostEstimate)
async def estimate_cost(
    feature: str = Query(...),
    scope_type: str | None = Query(None),
    scope_id: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    repo_ids: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Estimate token usage and cost without calling Claude."""
    parsed_repo_ids = [int(x) for x in repo_ids.split(",") if x.strip()] if repo_ids else None
    return await estimate_analysis_cost(
        db, feature, scope_type, scope_id, date_from, date_to,
        repo_ids=parsed_repo_ids,
    )


@router.post(
    "/ai/analyze",
    response_model=AIAnalysisResponse,
    status_code=201,
)
async def trigger_analysis(
    request: AIAnalyzeRequest,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await run_analysis(
            db=db,
            analysis_type=request.analysis_type.value,
            scope_type=request.scope_type.value,
            scope_id=request.scope_id,
            date_from=request.date_from,
            date_to=request.date_to,
            force=force,
            repo_ids=request.repo_ids,
        )
    except AIFeatureDisabledError as e:
        raise HTTPException(status_code=403, detail=e.detail)
    except AIBudgetExceededError as e:
        raise HTTPException(status_code=429, detail=e.detail)
    # Compute reused flag for response
    resp = AIAnalysisResponse.model_validate(result)
    resp.reused = result.reused_from_id is not None
    return resp


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
    rows = result.scalars().all()
    return [
        AIAnalysisResponse(
            **{c.key: getattr(r, c.key) for c in AIAnalysis.__table__.columns},
            reused=r.reused_from_id is not None,
        )
        for r in rows
    ]


@router.get("/ai/history/{analysis_id}", response_model=AIAnalysisResponse)
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
):
    analysis = await db.get(AIAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    resp = AIAnalysisResponse.model_validate(analysis)
    resp.reused = analysis.reused_from_id is not None
    return resp


@router.post(
    "/ai/one-on-one-prep",
    response_model=AIAnalysisResponse,
    status_code=201,
)
async def one_on_one_prep(
    request: OneOnOnePrepRequest,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, request.developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    try:
        result = await run_one_on_one_prep(
            db=db,
            developer_id=request.developer_id,
            date_from=request.date_from,
            date_to=request.date_to,
            force=force,
            repo_ids=request.repo_ids,
        )
    except AIFeatureDisabledError as e:
        raise HTTPException(status_code=403, detail=e.detail)
    except AIBudgetExceededError as e:
        raise HTTPException(status_code=429, detail=e.detail)
    resp = AIAnalysisResponse.model_validate(result)
    resp.reused = result.reused_from_id is not None
    return resp


@router.post(
    "/ai/team-health",
    response_model=AIAnalysisResponse,
    status_code=201,
)
async def team_health(
    request: TeamHealthRequest,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await run_team_health(
            db=db,
            team=request.team,
            date_from=request.date_from,
            date_to=request.date_to,
            force=force,
            repo_ids=request.repo_ids,
        )
    except AIFeatureDisabledError as e:
        raise HTTPException(status_code=403, detail=e.detail)
    except AIBudgetExceededError as e:
        raise HTTPException(status_code=429, detail=e.detail)
    resp = AIAnalysisResponse.model_validate(result)
    resp.reused = result.reused_from_id is not None
    return resp


# --- AI Analysis Schedules ---


def _schedule_response(schedule) -> AIScheduleResponse:
    """Build AIScheduleResponse with computed next_run_description."""
    resp = AIScheduleResponse.model_validate(schedule)
    resp.next_run_description = compute_next_run_description(schedule)
    return resp


@router.get("/ai/schedules", response_model=list[AIScheduleResponse])
async def list_ai_schedules(db: AsyncSession = Depends(get_db)):
    """List all AI analysis schedules."""
    schedules = await list_schedules(db)
    return [_schedule_response(s) for s in schedules]


@router.post(
    "/ai/schedules",
    response_model=AIScheduleResponse,
    status_code=201,
)
async def create_ai_schedule(
    data: AIScheduleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Create a new AI analysis schedule and register it with the scheduler."""
    schedule = await create_schedule(db, data, created_by=user.github_username)

    # Register with APScheduler
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        from app.main import register_schedule_job
        register_schedule_job(scheduler, schedule)

    return _schedule_response(schedule)


@router.patch("/ai/schedules/{schedule_id}", response_model=AIScheduleResponse)
async def update_ai_schedule(
    schedule_id: int,
    data: AIScheduleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update an AI analysis schedule and re-register with the scheduler."""
    schedule = await update_schedule(db, schedule_id, data)

    # Re-register with APScheduler
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        from app.main import register_schedule_job
        register_schedule_job(scheduler, schedule)

    return _schedule_response(schedule)


@router.delete("/ai/schedules/{schedule_id}", status_code=204)
async def delete_ai_schedule(
    schedule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete an AI analysis schedule and remove it from the scheduler."""
    await delete_schedule(db, schedule_id)

    # Remove from APScheduler
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler:
        try:
            scheduler.remove_job(f"ai_schedule_{schedule_id}")
        except Exception:
            pass

    return Response(status_code=204)


@router.post(
    "/ai/schedules/{schedule_id}/run",
    response_model=AIAnalysisResponse,
    status_code=201,
)
async def run_ai_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an AI analysis schedule."""
    schedule = await get_schedule(db, schedule_id)
    try:
        result = await run_scheduled_analysis(db, schedule)
    except AIFeatureDisabledError as e:
        raise HTTPException(status_code=403, detail=e.detail)
    except AIBudgetExceededError as e:
        raise HTTPException(status_code=429, detail=e.detail)
    resp = AIAnalysisResponse.model_validate(result)
    resp.reused = result.reused_from_id is not None
    return resp
