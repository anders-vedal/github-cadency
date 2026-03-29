"""Slack integration API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, require_admin
from app.models.database import get_db
from app.schemas.schemas import (
    AuthUser,
    NotificationHistoryResponse,
    NotificationLogResponse,
    SlackConfigResponse,
    SlackConfigUpdate,
    SlackTestResponse,
    SlackUserSettingsResponse,
    SlackUserSettingsUpdate,
)
from app.services.slack import (
    build_config_response,
    get_notification_history,
    get_slack_config,
    get_slack_user_settings,
    send_test_message,
    update_slack_config,
    update_slack_user_settings,
)

router = APIRouter()


# --- Admin-only: Global config ---


@router.get("/slack/config", response_model=SlackConfigResponse, dependencies=[Depends(require_admin)])
async def get_config(db: AsyncSession = Depends(get_db)):
    """Get global Slack configuration (admin only)."""
    config = await get_slack_config(db)
    return SlackConfigResponse(**build_config_response(config))


@router.patch("/slack/config", response_model=SlackConfigResponse, dependencies=[Depends(require_admin)])
async def patch_config(
    updates: SlackConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Update global Slack configuration (admin only)."""
    config = await update_slack_config(db, updates, updated_by=user.github_username)
    return SlackConfigResponse(**build_config_response(config))


@router.post("/slack/test", response_model=SlackTestResponse, dependencies=[Depends(require_admin)])
async def test_connection(db: AsyncSession = Depends(get_db)):
    """Send a test message to verify Slack connection (admin only)."""
    result = await send_test_message(db)
    return SlackTestResponse(**result)


@router.get("/slack/notifications", response_model=NotificationHistoryResponse, dependencies=[Depends(require_admin)])
async def get_notifications(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get notification history log (admin only)."""
    notifications, total = await get_notification_history(db, limit, offset)
    return NotificationHistoryResponse(
        notifications=[NotificationLogResponse.model_validate(n) for n in notifications],
        total=total,
    )


# --- Per-user: Slack notification preferences ---


@router.get("/slack/user-settings", response_model=SlackUserSettingsResponse)
async def get_my_slack_settings(
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Get current user's Slack notification preferences."""
    settings = await get_slack_user_settings(db, user.developer_id)
    return SlackUserSettingsResponse.model_validate(settings)


@router.patch("/slack/user-settings", response_model=SlackUserSettingsResponse)
async def patch_my_slack_settings(
    updates: SlackUserSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Update current user's Slack notification preferences."""
    settings = await update_slack_user_settings(db, user.developer_id, updates)
    return SlackUserSettingsResponse.model_validate(settings)


@router.get(
    "/slack/user-settings/{developer_id}",
    response_model=SlackUserSettingsResponse,
    dependencies=[Depends(require_admin)],
)
async def get_developer_slack_settings(
    developer_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get any developer's Slack notification preferences (admin only)."""
    settings = await get_slack_user_settings(db, developer_id)
    return SlackUserSettingsResponse.model_validate(settings)
