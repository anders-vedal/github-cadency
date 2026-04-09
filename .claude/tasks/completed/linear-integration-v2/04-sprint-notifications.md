# Phase 4: Sprint-Aware Notification Alerts

> Priority: Medium | Effort: Medium | Impact: Medium
> Prerequisite: Phase 1 (bugfixes)
> Independent of: Phase 2, 3, 5
> Related: `backend/app/services/notifications.py`

## Status: Completed

## Problem

The notification center has 16 alert types across 10 evaluators — all evaluating GitHub data only. When a team uses Linear for sprint planning, there are no alerts for:

- Sprint velocity declining over time
- Scope creep exceeding threshold mid-sprint
- Sprint at risk of missing commitment (low completion rate mid-cycle)
- Triage queue growing (issues stuck in triage)
- Estimation accuracy trending down
- Linear sync failures (distinct from GitHub sync)

These are high-signal alerts that engineering managers actively want. The data already exists in `sprint_stats.py` — it just needs evaluator functions wired into the notification framework.

## New Alert Types

### 4.1 `velocity_declining`

**Trigger:** Velocity trend shows >20% decline over last 5 sprints (configurable threshold).

**Evaluator logic:**
1. Call `get_sprint_velocity(db, limit=5)`
2. Compare first-half avg vs second-half avg (same logic as existing trend detection)
3. If decline exceeds threshold → create/update notification

**Severity:** `warning`
**Entity:** None (team-level alert)
**Auto-resolve:** When velocity trend stabilizes or improves
**Configurable threshold:** `velocity_decline_pct` (default: 20)

### 4.2 `scope_creep_high`

**Trigger:** Most recent closed sprint had scope creep > threshold (default: 25%).

**Evaluator logic:**
1. Call `get_scope_creep(db, limit=1)`
2. If `scope_creep_pct > threshold` → create notification

**Severity:** `warning`
**Entity:** Link to sprint detail page
**Auto-resolve:** When next sprint's scope creep is below threshold
**Configurable threshold:** `scope_creep_pct` (default: 25)

### 4.3 `sprint_at_risk`

**Trigger:** Active sprint with completion rate below threshold at >50% elapsed time.

**Evaluator logic:**
1. Find active sprint (`ExternalSprint.state == 'active'`)
2. Calculate elapsed percentage: `(now - start_date) / (end_date - start_date)`
3. If elapsed > 50% and completion rate < threshold → alert

**Severity:** `critical` if elapsed > 75% and completion < 50%, else `warning`
**Entity:** Link to sprint dashboard
**Auto-resolve:** When sprint closes or completion catches up
**Configurable threshold:** `sprint_risk_completion_pct` (default: 50)

### 4.4 `triage_queue_growing`

**Trigger:** Issues in triage exceeds threshold (default: 10) or avg triage duration exceeds threshold (default: 48h).

**Evaluator logic:**
1. Call `get_triage_metrics(db)`
2. If `issues_in_triage > count_threshold` OR `avg_triage_hours > duration_threshold` → alert

**Severity:** `warning`
**Entity:** Link to planning insights triage section
**Auto-resolve:** When both metrics drop below thresholds
**Configurable thresholds:** `triage_queue_max` (default: 10), `triage_duration_hours_max` (default: 48)

### 4.5 `estimation_accuracy_low`

**Trigger:** Estimation accuracy trend declining below threshold over last 5 sprints.

**Evaluator logic:**
1. Call `get_estimation_accuracy(db, limit=5)`
2. If average accuracy < threshold → alert

**Severity:** `info`
**Entity:** Link to planning insights accuracy chart
**Auto-resolve:** When accuracy improves above threshold
**Configurable threshold:** `estimation_accuracy_min_pct` (default: 60)

### 4.6 `linear_sync_failure`

**Trigger:** Most recent Linear `SyncEvent` has `status='failed'`.

**Evaluator logic:**
1. Query most recent `SyncEvent` where `sync_type='linear'`
2. If `status == 'failed'` → alert with error message in metadata

**Severity:** `warning`
**Entity:** Link to integration settings
**Auto-resolve:** When next Linear sync succeeds
**No configurable threshold** (binary: failed or not)

## Implementation

### Add to `ALERT_TYPE_META` registry

**File:** `backend/app/services/notifications.py`

```python
ALERT_TYPE_META = {
    # ... existing 16 types ...
    "velocity_declining": {
        "label": "Velocity Declining",
        "description": "Sprint velocity has declined significantly over recent sprints",
        "category": "Planning",
        "default_enabled": True,
        "thresholds": {"velocity_decline_pct": 20},
    },
    "scope_creep_high": {
        "label": "High Scope Creep", 
        "description": "Recent sprint had excessive mid-cycle scope additions",
        "category": "Planning",
        "default_enabled": True,
        "thresholds": {"scope_creep_pct": 25},
    },
    "sprint_at_risk": {
        "label": "Sprint At Risk",
        "description": "Active sprint is behind on completion with limited time remaining",
        "category": "Planning",
        "default_enabled": True,
        "thresholds": {"sprint_risk_completion_pct": 50},
    },
    "triage_queue_growing": {
        "label": "Triage Queue Growing",
        "description": "Too many issues waiting for triage or taking too long to triage",
        "category": "Planning",
        "default_enabled": True,
        "thresholds": {"triage_queue_max": 10, "triage_duration_hours_max": 48},
    },
    "estimation_accuracy_low": {
        "label": "Estimation Accuracy Low",
        "description": "Sprint estimation accuracy is trending below acceptable levels",
        "category": "Planning",
        "default_enabled": True,
        "thresholds": {"estimation_accuracy_min_pct": 60},
    },
    "linear_sync_failure": {
        "label": "Linear Sync Failed",
        "description": "Most recent Linear data sync failed",
        "category": "System",
        "default_enabled": True,
        "thresholds": {},
    },
}
```

### Evaluator function

Add `_evaluate_planning_alerts()` to `notifications.py`. This single evaluator handles all 6 new alert types. It short-circuits immediately if no active Linear integration exists (zero DB queries in that case).

```python
async def _evaluate_planning_alerts(db: AsyncSession, config: NotificationConfig) -> list[Notification]:
    """Evaluate sprint/planning alerts. No-op if Linear not configured."""
    # Check for active Linear integration first
    integration = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.type == "linear",
            IntegrationConfig.status == "active"
        )
    )
    if not integration.scalar_one_or_none():
        return []
    
    alerts = []
    # ... evaluate each type using sprint_stats.py functions
    return alerts
```

### Register in evaluation loop

Add `_evaluate_planning_alerts` to the main `evaluate_notifications()` orchestrator function, alongside the existing 10 evaluators.

### Post-sync hook

The existing evaluation runs post-GitHub-sync and on a 15-minute schedule. Add a post-Linear-sync hook: after `run_linear_sync()` completes successfully, trigger `evaluate_notifications()` (or at minimum `_evaluate_planning_alerts()`). This ensures sprint alerts are evaluated immediately after fresh data arrives.

### Frontend: Notification Settings

**File:** `frontend/src/pages/settings/NotificationSettings.tsx`

Add a "Planning" category group to the alert type cards (alongside existing Code Review, Workload, Risk, Collaboration, Trend, System groups). Each new alert type gets an enable toggle and threshold inputs, same pattern as existing types.

## Acceptance Criteria

- [ ] 6 new alert types registered in `ALERT_TYPE_META`
- [ ] `_evaluate_planning_alerts()` evaluator implemented and registered
- [ ] Evaluator is a no-op when Linear is not configured (zero overhead)
- [ ] Each alert type has auto-resolution logic
- [ ] Configurable thresholds stored in `notification_config`
- [ ] Post-Linear-sync evaluation hook added
- [ ] Notification Settings page shows "Planning" category with new alert types
- [ ] All existing notification tests pass
- [ ] New tests cover each alert type evaluation

## Test Plan

- Unit test: each evaluator returns correct alert when threshold exceeded
- Unit test: each evaluator returns no alert when below threshold
- Unit test: auto-resolution clears alerts when conditions improve
- Unit test: evaluator returns empty list when no Linear integration
- Integration test: `POST /notifications/evaluate` includes planning alerts
- Integration test: notification settings API includes new threshold fields
