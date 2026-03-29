from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.models.database import get_db
from app.models.models import AIAnalysis, Developer
from app.schemas.schemas import (
    AICostEstimate,
    AIAnalysisResponse,
    AIAnalyzeRequest,
    AISettingsResponse,
    AISettingsUpdate,
    AIUsageSummary,
    AuthUser,
    OneOnOnePrepRequest,
    TeamHealthRequest,
)
from app.services.ai_analysis import run_analysis, run_one_on_one_prep, run_team_health
from app.services.exceptions import AIBudgetExceededError, AIFeatureDisabledError
from app.services.ai_settings import (
    build_settings_response,
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
    db: AsyncSession = Depends(get_db),
):
    """Estimate token usage and cost without calling Claude."""
    from datetime import datetime, timedelta, timezone

    from app.services.ai_settings import compute_cost as calc_cost, get_ai_settings

    ai_settings = await get_ai_settings(db)

    # Parse dates with defaults
    now = datetime.now(timezone.utc)
    df = datetime.fromisoformat(date_from) if date_from else now - timedelta(days=30)
    dt = datetime.fromisoformat(date_to) if date_to else now

    est_input = 0
    est_output = 0
    data_items = 0
    note = ""

    if feature == "general_analysis":
        from app.services.ai_analysis import _gather_scope_texts

        if scope_type and scope_id:
            items, _ = await _gather_scope_texts(db, scope_type, scope_id, df, dt)
            data_items = len(items)
            # Rough estimate: each item ~125 tokens avg (500 chars / 4)
            est_input = data_items * 125 + 150  # +150 for system prompt
            est_output = 2000
            note = f"Based on {data_items} data items in scope"
        else:
            note = "Provide scope_type and scope_id for accurate estimate"

    elif feature == "one_on_one_prep":
        est_input = 5000
        est_output = 3000
        data_items = 1
        note = "Fixed estimate based on typical 1:1 context size"

    elif feature == "team_health":
        from app.models.models import Developer
        from sqlalchemy import func as sqlfunc

        dev_count_q = select(sqlfunc.count()).select_from(Developer).where(Developer.is_active.is_(True))
        dev_count = (await db.execute(dev_count_q)).scalar_one()
        est_input = dev_count * 200 + 3000
        est_output = 3000
        data_items = dev_count
        note = f"Based on {dev_count} active developers"

    elif feature == "work_categorization":
        from app.models.models import Issue, PullRequest

        # Count items that would be classified as unknown
        est_input = 200 * 10 + 60  # max batch size * avg title tokens + system
        est_output = 200 * 5
        data_items = 200
        note = "Max estimate (200 items per batch)"

    cost = calc_cost(
        est_input, est_output,
        ai_settings.input_token_price_per_million,
        ai_settings.output_token_price_per_million,
    )

    return AICostEstimate(
        estimated_input_tokens=est_input,
        estimated_output_tokens=est_output,
        estimated_cost_usd=round(cost, 4),
        data_items=data_items,
        note=note,
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
        )
    except AIFeatureDisabledError as e:
        raise HTTPException(status_code=403, detail=e.detail)
    except AIBudgetExceededError as e:
        raise HTTPException(status_code=429, detail=e.detail)
    resp = AIAnalysisResponse.model_validate(result)
    resp.reused = result.reused_from_id is not None
    return resp
