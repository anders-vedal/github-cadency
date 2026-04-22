"""Integration configuration API routes (Linear, etc.)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger

logger = get_logger(__name__)

from app.api.auth import get_current_user, require_admin
from app.models.database import get_db
from app.schemas.schemas import (
    AuthUser,
    DeveloperIdentityMapResponse,
    IntegrationConfigCreate,
    IntegrationConfigResponse,
    IntegrationConfigUpdate,
    IntegrationSyncStatusResponse,
    IntegrationTestResponse,
    IssueSourceResponse,
    LinearUserListResponse,
    LinkageRateTrendResponse,
    LinkQualitySummary,
    MapUserRequest,
    RelinkResponse,
)
from app.services.linear_sync import (
    create_integration,
    delete_integration,
    get_active_linear_integration,
    get_integration,
    get_primary_issue_source,
    list_linear_users,
    map_user,
    run_linear_relink,
    run_linear_sync,
    set_primary_issue_source,
    test_linear_connection,
    update_integration,
)
from app.services.linkage_quality import get_link_quality_summary, get_linkage_rate_trend

router = APIRouter()


def _build_response(config) -> dict:
    """Build response dict from IntegrationConfig, masking sensitive fields."""
    return {
        "id": config.id,
        "type": config.type,
        "display_name": config.display_name,
        "api_key_configured": bool(config.api_key),
        "workspace_id": config.workspace_id,
        "workspace_name": config.workspace_name,
        "status": config.status,
        "error_message": config.error_message,
        "is_primary_issue_source": config.is_primary_issue_source,
        "last_synced_at": config.last_synced_at,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


@router.post(
    "/integrations",
    response_model=IntegrationConfigResponse,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_integration_config(
    body: IntegrationConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new integration configuration (admin only)."""
    config = await create_integration(db, body.type, body.display_name, body.api_key)
    return IntegrationConfigResponse(**_build_response(config))


@router.get(
    "/integrations",
    response_model=list[IntegrationConfigResponse],
    dependencies=[Depends(require_admin)],
)
async def list_integrations(db: AsyncSession = Depends(get_db)):
    """List all configured integrations (admin only)."""
    from sqlalchemy import select
    from app.models.models import IntegrationConfig

    result = await db.execute(select(IntegrationConfig).order_by(IntegrationConfig.id))
    configs = result.scalars().all()
    return [IntegrationConfigResponse(**_build_response(c)) for c in configs]


@router.get(
    "/integrations/issue-source",
    response_model=IssueSourceResponse,
    dependencies=[Depends(require_admin)],
)
async def get_issue_source(db: AsyncSession = Depends(get_db)):
    """Get the current primary issue source (admin only)."""
    source = await get_primary_issue_source(db)
    integration = await get_active_linear_integration(db) if source == "linear" else None
    return IssueSourceResponse(
        source=source,
        integration_id=integration.id if integration else None,
    )


@router.patch(
    "/integrations/{integration_id}",
    response_model=IntegrationConfigResponse,
    dependencies=[Depends(require_admin)],
)
async def patch_integration(
    integration_id: int,
    body: IntegrationConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update integration configuration (admin only)."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    updates = body.model_dump(exclude_unset=True)
    config = await update_integration(db, config, updates)
    return IntegrationConfigResponse(**_build_response(config))


@router.delete(
    "/integrations/{integration_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
async def remove_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove an integration and all its synced data (admin only)."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    await delete_integration(db, config)


@router.post(
    "/integrations/{integration_id}/test",
    response_model=IntegrationTestResponse,
    dependencies=[Depends(require_admin)],
)
async def test_connection(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Test integration connection (admin only)."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    result = await test_linear_connection(db, config)
    return IntegrationTestResponse(**result)


@router.post(
    "/integrations/{integration_id}/sync",
    status_code=202,
    dependencies=[Depends(require_admin)],
)
async def trigger_sync(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a manual sync for this integration (admin only)."""
    import asyncio

    from app.models.database import AsyncSessionLocal

    from sqlalchemy import select as sa_select
    from app.models.models import SyncEvent

    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    if config.status != "active":
        raise HTTPException(status_code=400, detail="Integration is not active")

    # Check for already-running Linear sync
    active_sync = (await db.execute(
        sa_select(SyncEvent.id).where(
            SyncEvent.sync_type == "linear",
            SyncEvent.status == "started",
        ).limit(1)
    )).scalar_one_or_none()
    if active_sync:
        raise HTTPException(status_code=409, detail="Linear sync already in progress")

    # Run sync in background with its own session (request-scoped session will close)
    async def _bg_sync():
        try:
            async with AsyncSessionLocal() as bg_db:
                await run_linear_sync(bg_db, integration_id)
        except Exception as e:
            from app.main import _classifier, _reporter

            classified = _classifier.classify(e)
            logger.error(
                "Background Linear sync failed",
                error=str(e)[:200],
                exc_type=type(e).__name__,
                error_category=classified.category.value,
                integration_id=integration_id,
                event_type="system.sync",
                exc_info=e,
            )
            if classified.category.value == "app_bug" and _reporter:
                _reporter.record(
                    e,
                    component="services.linear_sync",
                    endpoint_path="/api/integrations/sync",
                    trigger_type="event",
                )

    asyncio.create_task(_bg_sync())
    return {"message": "Sync started"}


@router.get(
    "/integrations/{integration_id}/status",
    response_model=IntegrationSyncStatusResponse,
    dependencies=[Depends(require_admin)],
)
async def get_sync_status(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get sync status for this integration (admin only)."""
    from sqlalchemy import select
    from app.models.models import SyncEvent, ExternalIssue, ExternalSprint, ExternalProject

    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Check for active sync
    from sqlalchemy import func

    result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.sync_type == "linear", SyncEvent.status == "started")
        .order_by(SyncEvent.started_at.desc())
        .limit(1)
    )
    active_sync = result.scalar_one_or_none()

    # Last completed sync
    result = await db.execute(
        select(SyncEvent)
        .where(SyncEvent.sync_type == "linear", SyncEvent.status.in_(["completed", "completed_with_errors", "failed"]))
        .order_by(SyncEvent.completed_at.desc())
        .limit(1)
    )
    last_sync = result.scalar_one_or_none()

    # Counts
    issues_count = (await db.execute(
        select(func.count()).where(ExternalIssue.integration_id == integration_id)
    )).scalar() or 0
    sprints_count = (await db.execute(
        select(func.count()).where(ExternalSprint.integration_id == integration_id)
    )).scalar() or 0
    projects_count = (await db.execute(
        select(func.count()).where(ExternalProject.integration_id == integration_id)
    )).scalar() or 0

    return IntegrationSyncStatusResponse(
        is_syncing=active_sync is not None,
        last_sync_event_id=last_sync.id if last_sync else None,
        last_synced_at=config.last_synced_at,
        last_sync_status=last_sync.status if last_sync else None,
        issues_synced=issues_count,
        sprints_synced=sprints_count,
        projects_synced=projects_count,
    )


@router.get(
    "/integrations/{integration_id}/users",
    response_model=LinearUserListResponse,
    dependencies=[Depends(require_admin)],
)
async def get_linear_users(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
):
    """List Linear workspace users for developer mapping (admin only)."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    if config.type != "linear":
        raise HTTPException(status_code=400, detail="Not a Linear integration")
    result = await list_linear_users(db, config)
    return LinearUserListResponse(**result)


@router.post(
    "/integrations/{integration_id}/map-user",
    response_model=DeveloperIdentityMapResponse,
    dependencies=[Depends(require_admin)],
)
async def map_linear_user(
    integration_id: int,
    body: MapUserRequest,
    db: AsyncSession = Depends(get_db),
):
    """Map a Linear user to a DevPulse developer (admin only)."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    mapping = await map_user(db, config, body.external_user_id, body.developer_id)
    return DeveloperIdentityMapResponse.model_validate(mapping)


@router.patch(
    "/integrations/{integration_id}/primary",
    response_model=IntegrationConfigResponse,
    dependencies=[Depends(require_admin)],
)
async def set_primary(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Set this integration as the primary issue source (admin only)."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    if config.status != "active":
        raise HTTPException(status_code=400, detail="Integration must be active to set as primary")
    config = await set_primary_issue_source(db, integration_id)
    return IntegrationConfigResponse(**_build_response(config))


@router.get(
    "/integrations/{integration_id}/linkage-quality",
    response_model=LinkQualitySummary,
    dependencies=[Depends(require_admin)],
)
async def linkage_quality(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Admin-only linkage health summary (Phase 02)."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    if config.type != "linear":
        raise HTTPException(status_code=400, detail="Not a Linear integration")
    summary = await get_link_quality_summary(db, integration_id=integration_id)
    return LinkQualitySummary(**summary)


@router.post(
    "/integrations/{integration_id}/relink",
    response_model=RelinkResponse,
    dependencies=[Depends(require_admin)],
)
async def trigger_relink(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Rerun the 4-pass PR↔issue linker (Phase 02). Admin only. Idempotent."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    if config.type != "linear":
        raise HTTPException(status_code=400, detail="Not a Linear integration")
    sync_event = await run_linear_relink(db, integration_id)
    return RelinkResponse(
        sync_event_id=sync_event.id,
        status=sync_event.status,
    )


@router.get(
    "/integrations/{integration_id}/linkage-quality/trend",
    response_model=LinkageRateTrendResponse,
    dependencies=[Depends(require_admin)],
)
async def linkage_quality_trend(
    integration_id: int,
    weeks: int = Query(12, ge=2, le=52),
    db: AsyncSession = Depends(get_db),
):
    """Weekly linkage-rate trend for the last ``weeks`` weeks (Phase 02 deviation)."""
    config = await get_integration(db, integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    if config.type != "linear":
        raise HTTPException(status_code=400, detail="Not a Linear integration")
    buckets = await get_linkage_rate_trend(
        db, integration_id=integration_id, weeks=weeks
    )
    return LinkageRateTrendResponse(buckets=buckets)
