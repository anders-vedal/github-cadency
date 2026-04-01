"""Notification center API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import AuthUser, get_current_user, require_admin
from app.models.database import get_db
from app.rate_limit import limiter
from app.schemas.schemas import (
    DismissAlertTypeRequest,
    DismissNotificationRequest,
    EvaluationResultResponse,
    NotificationConfigResponse,
    NotificationConfigUpdate,
    NotificationsListResponse,
)
from app.services.notifications import (
    ALERT_TYPE_META,
    build_config_response,
    dismiss_alert_type,
    dismiss_notification,
    evaluate_all_alerts,
    get_active_notifications,
    get_notification_config,
    mark_all_read,
    mark_read,
    undismiss_alert_type,
    undismiss_notification,
    update_notification_config,
)

_VALID_SEVERITIES = {"critical", "warning", "info"}

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=NotificationsListResponse,
    dependencies=[Depends(require_admin)],
)
async def list_notifications(
    severity: str | None = None,
    alert_type: str | None = None,
    include_dismissed: bool = False,
    limit: int = 50,
    offset: int = 0,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if severity is not None and severity not in _VALID_SEVERITIES:
        raise HTTPException(
            status_code=422,
            detail=f"severity must be one of: {', '.join(sorted(_VALID_SEVERITIES))}",
        )
    if alert_type is not None and alert_type not in ALERT_TYPE_META:
        raise HTTPException(
            status_code=422,
            detail=f"alert_type must be one of: {', '.join(sorted(ALERT_TYPE_META))}",
        )
    return await get_active_notifications(
        db, user.developer_id, severity, alert_type, include_dismissed, limit, offset
    )


@router.post("/{notification_id}/read", dependencies=[Depends(require_admin)])
async def read_notification(
    notification_id: int,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await mark_read(db, notification_id, user.developer_id)
    return {"success": True}


@router.post("/read-all", dependencies=[Depends(require_admin)])
async def read_all_notifications(
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await mark_all_read(db, user.developer_id)
    return {"marked_read": count}


@router.post("/{notification_id}/dismiss", dependencies=[Depends(require_admin)])
async def dismiss_single_notification(
    notification_id: int,
    body: DismissNotificationRequest,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await dismiss_notification(
        db, notification_id, user.developer_id,
        body.dismiss_type, body.duration_days,
    )


@router.post("/dismiss-type", dependencies=[Depends(require_admin)])
async def dismiss_notification_type(
    body: DismissAlertTypeRequest,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.alert_type not in ALERT_TYPE_META:
        raise HTTPException(
            status_code=422,
            detail=f"alert_type must be one of: {', '.join(sorted(ALERT_TYPE_META))}",
        )
    return await dismiss_alert_type(
        db, body.alert_type, user.developer_id,
        body.dismiss_type, body.duration_days,
    )


@router.delete("/dismissals/{dismissal_id}", dependencies=[Depends(require_admin)])
async def undo_dismiss(
    dismissal_id: int,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await undismiss_notification(db, dismissal_id, user.developer_id)
    return {"success": True}


@router.delete("/type-dismissals/{dismissal_id}", dependencies=[Depends(require_admin)])
async def undo_type_dismiss(
    dismissal_id: int,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await undismiss_alert_type(db, dismissal_id, user.developer_id)
    return {"success": True}


@router.get(
    "/config",
    response_model=NotificationConfigResponse,
    dependencies=[Depends(require_admin)],
)
async def get_config(db: AsyncSession = Depends(get_db)):
    config = await get_notification_config(db)
    return build_config_response(config)


@router.patch(
    "/config",
    response_model=NotificationConfigResponse,
    dependencies=[Depends(require_admin)],
)
async def update_config(
    body: NotificationConfigUpdate,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await update_notification_config(db, body, user.github_username)
    return build_config_response(config)


@router.post(
    "/evaluate",
    response_model=EvaluationResultResponse,
    dependencies=[Depends(require_admin)],
)
@limiter.limit("5/minute")
async def trigger_evaluation(request: Request, db: AsyncSession = Depends(get_db)):
    result = await evaluate_all_alerts(db)
    return result
