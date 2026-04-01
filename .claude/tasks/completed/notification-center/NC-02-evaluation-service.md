# Task NC-02: Notification Center — Alert Evaluation Service

## Phase
Notification Center v2

## Status
completed

## Blocked By
- NC-01-backend-models-migration

## Blocks
- NC-03-api-endpoints

## Description
Create the notification evaluation service that materializes alerts from all sources into the `notifications` table. Runs post-sync and on a scheduled interval. Applies contribution_category filtering to eliminate noise from system accounts. Auto-resolves notifications when conditions clear.

## Deliverables

### backend/app/services/notifications.py (new)

#### Core evaluation orchestrator
```python
async def evaluate_all_alerts(db: AsyncSession) -> dict:
    """Run all alert evaluators. Returns summary of created/updated/resolved counts."""
```
- Loads `NotificationConfig` singleton (using `db.get(NotificationConfig, 1)` pattern from ai_settings)
- Loads excluded contribution categories and resolves to excluded role_keys via `role_definitions` table
- Calls each evaluator in sequence, passing config + excluded developer IDs
- Returns `{"created": N, "updated": N, "resolved": N}` summary

#### Upsert + auto-resolve helpers
```python
async def _upsert_notification(
    db: AsyncSession,
    alert_key: str,
    alert_type: str,
    severity: str,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    link_path: str | None = None,
    developer_id: int | None = None,
    metadata: dict | None = None,
) -> Notification:
    """Create or update a notification by alert_key. If exists and resolved, re-open it."""

async def _auto_resolve_stale(
    db: AsyncSession,
    alert_type: str,
    active_keys: set[str],
) -> int:
    """Resolve any active notifications of this type whose alert_key is NOT in active_keys.
    Sets resolved_at = now(). Returns count resolved."""
```

#### Evaluator functions (each returns set of active alert_keys)

**`_evaluate_stale_pr_alerts(db, config, excluded_dev_ids) -> set[str]`**
- Query open, non-draft PRs with no first review older than `config.stale_pr_threshold_hours`
- Query PRs with CHANGES_REQUESTED and no author response
- Query approved-but-not-merged PRs
- Exclude PRs authored by excluded developers
- alert_key format: `stale_pr:pr:{pr_id}`
- severity: age < 72h = "warning", age >= 72h = "critical"
- link_path: PR's `html_url` (GitHub external link)
- title: "PR #{number} waiting {age} for review" / "PR #{number} has unresolved changes" / "PR #{number} approved but not merged"

**`_evaluate_workload_alerts(db, config, excluded_dev_ids) -> set[str]`**
Handles 4 alert types from the current `get_workload()` logic, but filtered:
- `review_bottleneck`: reviews > `config.review_bottleneck_multiplier` * team median
  - alert_key: `review_bottleneck:developer:{dev_id}`
  - severity: "warning"
  - link_path: `/team/{dev_id}`
- `underutilized`: 0 PRs authored and 0 reviews in last 30 days (only for `code_contributor` roles)
  - alert_key: `underutilized:developer:{dev_id}`
  - severity: "info"
  - link_path: `/team/{dev_id}`
- `uneven_assignment`: top 20% hold > 50% of open issues
  - alert_key: `uneven_assignment:team:{team_name or 'all'}`
  - severity: "warning"
  - link_path: `/insights/workload`
- `merged_without_approval`: PRs merged without approval in last 30 days
  - alert_key: `merged_without_approval:developer:{dev_id}`
  - severity: "warning"
  - link_path: `/team/{dev_id}`

**`_evaluate_revert_spike_alert(db, config, excluded_dev_ids) -> set[str]`**
- Revert rate > `config.revert_spike_threshold_pct`% of merged PRs (last 30 days)
- alert_key: `revert_spike:team:all`
- severity: "critical"
- link_path: `/insights/code-churn`

**`_evaluate_risk_alerts(db, config, excluded_dev_ids) -> set[str]`**
- Open PRs with risk_level >= `config.high_risk_pr_min_level`
- Uses `compute_pr_risk()` from `services/risk.py`
- alert_key: `high_risk_pr:pr:{pr_id}`
- severity: "critical" for critical risk, "warning" for high/medium
- link_path: PR's `html_url`
- metadata: `{"risk_score": 0.85, "risk_factors": [...]}`

**`_evaluate_collaboration_alerts(db, config) -> set[str]`**
- Bus factor: single reviewer handles >70% of reviews for a repo
  - alert_key: `bus_factor:repo:{repo_id}`
  - severity: "warning"
  - link_path: `/insights/collaboration`
- Team silos: two teams with zero cross-team reviews
  - alert_key: `team_silo:team:{team_a}:{team_b}`
  - severity: "info"
  - link_path: `/insights/collaboration`
- Isolated developers: minimal review interaction
  - alert_key: `isolated_developer:developer:{dev_id}`
  - severity: "info"
  - link_path: `/team/{dev_id}`

**`_evaluate_trend_alerts(db, config, excluded_dev_ids) -> set[str]`**
- Compare current 30-day period vs previous 30-day period per developer
- PRs merged dropped > `config.declining_trend_pr_drop_pct`%
- Review quality score dropped > `config.declining_trend_quality_drop_pct`%
- alert_key: `declining_trend:developer:{dev_id}`
- severity: "warning"
- link_path: `/team/{dev_id}`
- metadata: `{"reasons": ["PRs merged dropped 45%", "Review quality dropped 25%"]}`

**`_evaluate_issue_linkage_alerts(db, config, excluded_dev_ids) -> set[str]`**
- Developers with issue linkage rate below `config.issue_linkage_threshold_pct`%
- alert_key: `issue_linkage:developer:{dev_id}`
- severity: "info"
- link_path: `/team/{dev_id}`

**`_evaluate_ai_budget_alert(db, config) -> set[str]`**
- Check `AISettings.budget_pct_used >= AISettings.budget_warning_threshold`
- alert_key: `ai_budget:system:1`
- severity: "warning"
- link_path: `/admin/ai/settings`

**`_evaluate_sync_failure_alert(db, config) -> set[str]`**
- Most recent `SyncEvent` has status "failed" or "completed_with_errors"
- alert_key: `sync_failure:sync:{sync_event_id}`
- severity: "critical" for failed, "warning" for completed_with_errors
- link_path: `/admin/sync/{sync_event_id}`

**`_evaluate_config_alerts(db, config) -> set[str]`**
- Unassigned roles: count of active developers with `role = NULL`
  - alert_key: `unassigned_roles:system:count`
  - severity: "info"
  - link_path: `/admin/team`
  - metadata: `{"count": N}`
- Missing GitHub config: call `validate_github_config()`, create alert per error
  - alert_key: `missing_config:system:{field_name}`
  - severity: "critical" for errors, "warning" for warnings
  - link_path: `/admin/sync`
- Missing Slack token: check `SlackConfig.bot_token`
  - alert_key: `missing_config:slack:bot_token`
  - severity: "info"
  - link_path: `/admin/slack`
- Missing AI API key: check `ANTHROPIC_API_KEY`
  - alert_key: `missing_config:ai:api_key`
  - severity: "info"
  - link_path: `/admin/ai/settings`

#### Config helper
```python
async def get_notification_config(db: AsyncSession) -> NotificationConfig:
    """Get or create singleton notification config (id=1). Same pattern as get_ai_settings()."""

async def update_notification_config(
    db: AsyncSession, updates: NotificationConfigUpdate, updated_by: str
) -> NotificationConfig:
    """Partial update notification config. Same pattern as update_ai_settings()."""
```

#### Excluded developers helper
```python
async def _get_excluded_developer_ids(
    db: AsyncSession, excluded_categories: list[str]
) -> set[int]:
    """Resolve contribution categories to a set of developer IDs to exclude.
    Joins role_definitions (by contribution_category) -> developers (by role)."""
```

### backend/app/main.py (extend)
- Add scheduled job for notification evaluation:
  ```python
  scheduler.add_job(
      scheduled_notification_evaluation,
      "interval",
      minutes=15,  # loaded from NotificationConfig at startup
      id="notification_evaluation",
      misfire_grace_time=None,
  )
  ```
- Add `scheduled_notification_evaluation()` wrapper (similar to `scheduled_sync()`)
- Call `evaluate_all_alerts()` as a post-sync hook in `run_sync()` completion path

### backend/app/services/github_sync.py (extend)
- At the end of `run_sync()`, after `recompute_collaboration_scores()`, add:
  ```python
  # Evaluate notification alerts post-sync
  try:
      from app.services.notifications import evaluate_all_alerts
      await evaluate_all_alerts(db)
  except Exception as e:
      logger.warning("Post-sync notification evaluation failed", error=str(e), event_type="system.sync")
  ```
- Non-blocking — if evaluation fails, sync still completes (same pattern as collaboration recomputation)

### Design Notes
- Each evaluator collects the set of `alert_key`s that are currently active, then calls `_auto_resolve_stale()` to resolve any that are no longer active. This is the auto-resolution mechanism.
- Evaluators are independent and can fail individually without affecting others. Wrap each in try/except with warning log.
- The contribution category filter is loaded once per evaluation run and passed to all evaluators, not queried per-evaluator.
- For trend alerts, use the same `_linear_regression()` pattern from stats.py but simplified to period-over-period comparison.
- Stale PR evaluator reuses the query logic from `get_stale_prs()` in stats.py but adapted for the materialization pattern (writes to notifications table instead of returning response).
- Risk evaluator reuses `compute_pr_risk()` from risk.py directly — no duplication of risk scoring logic.
