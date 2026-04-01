# AC-01: Notification Backend Concerns

**Priority:** This week
**Severity:** Medium
**Effort:** Medium
**Status:** Pending

## Finding #1: Missing Alert Toggle Columns in notification_config

- **File:** `backend/app/models/models.py` (NotificationConfig), `backend/migrations/versions/033_add_notification_center.py`
- `ALERT_TYPE_META` in `services/notifications.py` defines 16 alert types, but `notification_config` table only has 14 `alert_*_enabled` toggle columns
- Missing: `alert_team_silo_enabled`, `alert_isolated_developer_enabled`
- Service works around this with `getattr(config, field, True)` fallback — these alerts are permanently un-togglable from the admin UI
- The `NotificationConfigUpdate` Pydantic schema also lacks these fields

### Required Changes
1. Create migration 034: add `alert_team_silo_enabled` and `alert_isolated_developer_enabled` Boolean columns with `server_default="true"` to `notification_config`
2. Add both columns to `NotificationConfig` ORM model in `models.py`
3. Add both fields to `NotificationConfigUpdate` and `NotificationConfigResponse` in `schemas.py`
4. Remove `getattr()` fallbacks in `_evaluate_collaboration_alerts()` — direct attribute access will now work

## Finding #2: evaluate_all_alerts() Returns Zeroed Counts

- **File:** `backend/app/services/notifications.py:1006-1058`
- `counts = {"created": 0, "updated": 0, "resolved": 0}` is initialized but never incremented
- The `EvaluationResultResponse` always returns `{"created": 0, "updated": 0, "resolved": 0}`
- Frontend "Evaluate now" button shows success but no meaningful result

### Required Changes
1. Have `_upsert_notification()` return a status string ("created" or "updated") — it already does
2. Increment `counts["created"]` or `counts["updated"]` based on return value in the evaluator loop
3. Have `_auto_resolve_stale()` return count — it already does
4. Accumulate resolved count across all evaluators
5. Alternatively: count active notifications before/after evaluation and compute delta

## Finding #3: In-Memory Pagination in get_active_notifications()

- **File:** `backend/app/services/notifications.py:1064-1175`
- Loads ALL active (unresolved) notifications into memory, applies dismiss/read state in Python, then slices for pagination
- Works fine for small teams but degrades with large notification volumes
- The dismiss/read state check requires cross-referencing 3 separate tables

### Required Changes
1. Use SQL-level pagination with subquery joins for dismiss/read state
2. Apply `LIMIT`/`OFFSET` at the query level after filtering
3. Compute `unread_count` and `counts_by_severity` via aggregate queries
4. This is a performance optimization — defer unless notification volume becomes a problem

## Finding #4: Notification Scheduler Not Reschedulable

- **File:** `backend/app/main.py:234-249`
- `evaluation_interval_minutes` loaded from `NotificationConfig` once at startup
- `PATCH /notifications/config` updates the DB value but does NOT reschedule the APScheduler job
- Contrast with sync schedule: `PATCH /sync/schedule` calls `reschedule_sync_jobs()` to live-update
- Change only takes effect after app restart

### Required Changes
1. Add `reschedule_notification_job()` to `main.py` (following the `reschedule_sync_jobs()` pattern)
2. Call it from the `PATCH /notifications/config` route when `evaluation_interval_minutes` changes
3. Access `app.state.scheduler` via the request's `app` reference

## Finding #5: Fragile Evaluator Dispatch Logic

- **File:** `backend/app/services/notifications.py:1028-1039`
- The evaluator loop uses `if evaluator in (...)` and `elif evaluator == ...` to determine which arguments to pass
- Some evaluators receive `(db, config, excluded_dev_ids)`, others `(db, config)` only
- Adding a new evaluator requires editing the dispatch logic carefully

### Required Changes
1. Standardize evaluator signatures to accept `(db, config, excluded_dev_ids)` — evaluators that don't need `excluded_dev_ids` can ignore it
2. Or use a registry pattern: `EVALUATORS = [(name, func, toggle_field, needs_exclusion)]`
3. This simplifies the loop to a uniform call pattern

## Finding #6: Webhooks Don't Trigger Notification Evaluation

- **File:** `backend/app/api/webhooks.py`
- Webhook handlers (PR, review, issue events) update DB state but never call `evaluate_all_alerts()`
- A PR becoming stale via webhook won't generate an alert until the next scheduled evaluation (up to 15 min) or next sync
- For time-sensitive alerts (stale PRs, high-risk PRs), this delay may be significant

### Required Changes
1. Option A: Call `evaluate_all_alerts(db)` at the end of webhook processing (adds latency to webhook response)
2. Option B: Fire evaluation as a background task after webhook commit
3. Option C: Accept 15-min delay — evaluation runs frequently enough for most use cases
4. Recommendation: Option C is pragmatic; document the delay as expected behavior
