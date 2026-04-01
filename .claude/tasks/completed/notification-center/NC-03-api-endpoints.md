# Task NC-03: Notification Center — API Endpoints

## Phase
Notification Center v2

## Status
completed

## Blocked By
- NC-01-backend-models-migration
- NC-02-evaluation-service

## Blocks
- NC-04-frontend-notification-center

## Description
Create the notification API router with endpoints for listing active notifications, marking as read, dismissing (instance and type-level), managing dismissals, admin config CRUD, and triggering evaluation. All endpoints are admin-only (matching current alert visibility).

## Deliverables

### backend/app/api/notifications.py (new)

Router: `APIRouter(prefix="/notifications", tags=["notifications"])`

#### `GET /notifications`
- Auth: `get_current_user` (admin only via `require_admin`)
- Query params:
  - `severity: str | None` — filter by severity
  - `alert_type: str | None` — filter by alert type
  - `include_dismissed: bool = False` — include dismissed notifications
  - `limit: int = 50` — max results
  - `offset: int = 0` — pagination
- Logic:
  - Query `Notification` where `resolved_at IS NULL`
  - LEFT JOIN `NotificationRead` for `is_read` computation (where user_id = current user)
  - LEFT JOIN `NotificationDismissal` for `is_dismissed` computation:
    - Dismissed if row exists AND (`dismiss_type = "permanent"` OR `expires_at > now()`)
  - LEFT JOIN `NotificationTypeDismissal` for type-level dismiss check:
    - Dismissed if row exists for this `alert_type` AND same expiry logic
  - Unless `include_dismissed=True`, filter out dismissed notifications
  - Order by: severity priority (critical=0, warning=1, info=2), then `created_at DESC`
  - Compute `unread_count` (active, not dismissed, not read)
  - Compute `counts_by_severity` from active non-dismissed notifications
- Response: `NotificationsListResponse`

#### `POST /notifications/{id}/read`
- Auth: `require_admin`
- Logic: Upsert `NotificationRead(notification_id=id, user_id=current_user.developer_id)`
- Response: `{"success": true}`
- Idempotent — re-reading a read notification is a no-op

#### `POST /notifications/read-all`
- Auth: `require_admin`
- Logic: Bulk insert `NotificationRead` for all active unread notifications for this user
- Response: `{"marked_read": N}`

#### `POST /notifications/{id}/dismiss`
- Auth: `require_admin`
- Body: `DismissNotificationRequest` — `{dismiss_type, duration_days?}`
- Logic:
  - Validate notification exists and is active (not resolved)
  - Compute `expires_at` from `duration_days` if temporary
  - Upsert `NotificationDismissal(notification_id=id, user_id=current_user.developer_id, ...)`
  - Also mark as read if not already
- Response: `{"success": true, "expires_at": ... | null}`

#### `POST /notifications/dismiss-type`
- Auth: `require_admin`
- Body: `DismissAlertTypeRequest` — `{alert_type, dismiss_type, duration_days?}`
- Logic:
  - Validate `alert_type` is a valid `AlertType` enum value
  - Upsert `NotificationTypeDismissal(alert_type=..., user_id=..., ...)`
- Response: `{"success": true, "alert_type": ..., "expires_at": ... | null}`

#### `DELETE /notifications/dismissals/{id}`
- Auth: `require_admin`
- Logic: Delete `NotificationDismissal` by id (only if `user_id` matches current user)
- Response: `{"success": true}`
- Use case: "un-dismiss" — bring a notification back

#### `DELETE /notifications/type-dismissals/{id}`
- Auth: `require_admin`
- Logic: Delete `NotificationTypeDismissal` by id (only if `user_id` matches current user)
- Response: `{"success": true}`

#### `GET /notifications/config`
- Auth: `require_admin`
- Logic: Call `get_notification_config(db)`
- Response: `NotificationConfigResponse`
  - Includes computed `alert_types` list with label, description, enabled state, and relevant thresholds per type
  - Alert type metadata registry (similar to `FEATURE_META` in ai_settings):
    ```python
    ALERT_TYPE_META = {
        "stale_pr": {
            "label": "Stale Pull Requests",
            "description": "PRs waiting too long for review, with unresolved changes, or approved but not merged",
            "thresholds": ["stale_pr_threshold_hours"],
        },
        "review_bottleneck": {
            "label": "Review Bottlenecks",
            "description": "Developers handling disproportionately more reviews than the team median",
            "thresholds": ["review_bottleneck_multiplier"],
        },
        # ... etc for all 16 types
    }
    ```

#### `PATCH /notifications/config`
- Auth: `require_admin`
- Body: `NotificationConfigUpdate`
- Logic: Call `update_notification_config(db, updates, user.github_username)`
- Response: `NotificationConfigResponse`
- Side effect: If `evaluation_interval_minutes` changed, reschedule the APScheduler job (same pattern as `reschedule_sync_jobs()`)

#### `POST /notifications/evaluate`
- Auth: `require_admin`
- Logic: Call `evaluate_all_alerts(db)` synchronously
- Response: `{"created": N, "updated": N, "resolved": N}`
- Use case: Admin clicks "Evaluate now" button after changing thresholds

### backend/app/main.py (extend)
- Import and register router:
  ```python
  from app.api import notifications
  app.include_router(notifications.router, prefix="/api", tags=["notifications"])
  ```

### backend/app/services/notifications.py (extend from NC-02)

#### Query helper for GET /notifications
```python
async def get_active_notifications(
    db: AsyncSession,
    user_id: int,
    severity: str | None = None,
    alert_type: str | None = None,
    include_dismissed: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> NotificationsListResponse:
    """Query active notifications with read/dismiss state for the given user."""
```
- Uses subqueries for `is_read` and `is_dismissed` to avoid N+1
- Handles expired temporary dismissals (ignores rows where `expires_at < now()`)
- Computes `unread_count` and `counts_by_severity` in a single additional aggregate query

#### Dismiss helpers
```python
async def dismiss_notification(db, notification_id, user_id, dismiss_type, duration_days) -> dict
async def dismiss_alert_type(db, alert_type, user_id, dismiss_type, duration_days) -> dict
async def undismiss_notification(db, dismissal_id, user_id) -> None
async def undismiss_alert_type(db, dismissal_id, user_id) -> None
async def mark_read(db, notification_id, user_id) -> None
async def mark_all_read(db, user_id) -> int
```

### backend/tests/integration/test_notifications_api.py (new)

Test cases:
1. `test_get_notifications_empty` — no notifications returns empty list with zero counts
2. `test_get_notifications_after_evaluation` — trigger evaluation, verify notifications appear
3. `test_notification_read_marking` — mark read, verify is_read=True and unread_count decrements
4. `test_notification_read_all` — bulk mark read
5. `test_notification_dismiss_permanent` — dismiss, verify excluded from default list
6. `test_notification_dismiss_temporary` — dismiss with duration, verify expires
7. `test_notification_dismiss_type` — dismiss alert type, verify all of that type hidden
8. `test_notification_undismiss` — delete dismissal, verify notification reappears
9. `test_notification_include_dismissed` — verify `include_dismissed=True` shows dismissed items
10. `test_notification_config_get` — verify config response includes alert_types metadata
11. `test_notification_config_update` — patch thresholds, verify updated
12. `test_notification_evaluate_endpoint` — POST evaluate, verify counts returned
13. `test_contribution_category_filtering` — create a developer with system role, verify their alerts are excluded
14. `test_auto_resolve_on_evaluation` — create condition, evaluate, resolve condition, re-evaluate, verify resolved_at set
15. `test_severity_ordering` — verify critical sorts before warning before info

### Design Notes
- The `GET /notifications` endpoint is the single source of truth for the frontend notification center. All alert data flows through this.
- Dismiss state is per-user — one admin dismissing doesn't affect other admins.
- The `ALERT_TYPE_META` registry drives the admin config page UI — the frontend doesn't need to hardcode alert type descriptions.
- Severity ordering uses a CASE expression in the query for consistent sort regardless of string collation.
- The old `GET /stats/workload` endpoint and `AlertStrip` component continue to work unchanged. The notification center is additive — it reads from the materialized `notifications` table, not from the workload endpoint. In a future cleanup, the Dashboard can stop calling the workload alerts and use the notification center data instead.
