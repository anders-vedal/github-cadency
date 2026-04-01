# Task NC-01: Notification Center — Database Models and Migration

## Phase
Notification Center v2

## Status
completed

## Blocked By
None

## Blocks
- NC-02-evaluation-service
- NC-03-api-endpoints

## Description
Create the database tables that power the unified notification center: materialized notifications with lifecycle tracking, per-user read/dismiss state, per-type dismissals, and an admin-configurable singleton for alert thresholds and toggles. Also adds contribution_category exclusion to filter noise from system accounts.

## Deliverables

### backend/app/models/models.py (extend)

#### `Notification` model
Materialized alert records with dedup and lifecycle management.
- `id` (Integer, PK)
- `alert_type` (String(50), NOT NULL, indexed) — e.g. "stale_pr", "review_bottleneck", "high_risk_pr", "bus_factor", "declining_trend", "issue_linkage", "ai_budget", "sync_failure", "unassigned_roles", "missing_config", "underutilized", "uneven_assignment", "merged_without_approval", "revert_spike", "team_silo", "isolated_developer"
- `alert_key` (String(200), UNIQUE, NOT NULL) — dedup key format: `{type}:{entity_type}:{entity_id}` e.g. "stale_pr:pr:123", "underutilized:developer:45", "bus_factor:repo:7"
- `severity` (String(20), NOT NULL) — "critical", "warning", "info"
- `title` (Text, NOT NULL) — human-readable short title
- `body` (Text, nullable) — detail text or explanation
- `entity_type` (String(50), nullable) — "pull_request", "developer", "repository", "team", "system"
- `entity_id` (Integer, nullable) — FK-less reference to the entity
- `link_path` (String(500), nullable) — frontend route e.g. "/team/45" or GitHub URL
- `developer_id` (Integer, FK -> developers, nullable, indexed) — who this alert is about (NULL for team/system-level)
- `metadata` (JSONB, nullable) — flexible extra data (risk factors, PR numbers, threshold values, etc.)
- `resolved_at` (DateTime(tz), nullable) — NULL = active, set = auto-resolved when condition clears
- `created_at` (DateTime(tz), server_default=now())
- `updated_at` (DateTime(tz), server_default=now(), onupdate)
- Indexes: `alert_type`, `severity`, `resolved_at`, `developer_id`, `created_at DESC`
- Composite index: `(alert_type, resolved_at)` for efficient "active alerts by type" queries

#### `NotificationRead` model
Tracks which users have seen each notification (separate from dismiss).
- `id` (Integer, PK)
- `notification_id` (Integer, FK -> notifications, NOT NULL)
- `user_id` (Integer, FK -> developers, NOT NULL)
- `read_at` (DateTime(tz), server_default=now())
- UniqueConstraint: `(notification_id, user_id)`
- Index: `user_id`

#### `NotificationDismissal` model
Per-instance dismissal with optional expiry.
- `id` (Integer, PK)
- `notification_id` (Integer, FK -> notifications, NOT NULL)
- `user_id` (Integer, FK -> developers, NOT NULL)
- `dismiss_type` (String(20), NOT NULL) — "permanent", "temporary"
- `expires_at` (DateTime(tz), nullable) — NULL for permanent, set for temporary
- `created_at` (DateTime(tz), server_default=now())
- UniqueConstraint: `(notification_id, user_id)`
- Index: `user_id`, `expires_at`

#### `NotificationTypeDismissal` model
Dismiss an entire alert type (e.g. "mute all underutilized alerts for 7 days").
- `id` (Integer, PK)
- `alert_type` (String(50), NOT NULL)
- `user_id` (Integer, FK -> developers, NOT NULL)
- `dismiss_type` (String(20), NOT NULL) — "permanent", "temporary"
- `expires_at` (DateTime(tz), nullable)
- `created_at` (DateTime(tz), server_default=now())
- UniqueConstraint: `(alert_type, user_id)`
- Index: `user_id`

#### `NotificationConfig` model (singleton, id=1)
Admin-configurable thresholds and toggles. Follows `AISettings`/`SlackConfig` singleton pattern.
- `id` (Integer, PK, always 1)
- Per-alert-type enable toggles (all `Boolean, server_default="true"`):
  - `alert_stale_pr_enabled`
  - `alert_review_bottleneck_enabled`
  - `alert_underutilized_enabled`
  - `alert_uneven_assignment_enabled`
  - `alert_merged_without_approval_enabled`
  - `alert_revert_spike_enabled`
  - `alert_high_risk_pr_enabled`
  - `alert_bus_factor_enabled`
  - `alert_declining_trends_enabled`
  - `alert_issue_linkage_enabled`
  - `alert_ai_budget_enabled`
  - `alert_sync_failure_enabled`
  - `alert_unassigned_roles_enabled`
  - `alert_missing_config_enabled`
- Configurable thresholds:
  - `stale_pr_threshold_hours` (Integer, server_default="48")
  - `review_bottleneck_multiplier` (Float, server_default="2.0") — alert when reviews > N * median
  - `revert_spike_threshold_pct` (Float, server_default="5.0")
  - `high_risk_pr_min_level` (String(20), server_default="high") — "medium", "high", "critical"
  - `issue_linkage_threshold_pct` (Float, server_default="20.0")
  - `declining_trend_pr_drop_pct` (Float, server_default="30.0") — PRs merged dropped > N%
  - `declining_trend_quality_drop_pct` (Float, server_default="20.0") — review quality dropped > N%
- Contribution category exclusion:
  - `exclude_contribution_categories` (JSONB, server_default='["system", "non_contributor"]')
- Evaluation schedule:
  - `evaluation_interval_minutes` (Integer, server_default="15")
- Timestamps:
  - `updated_at` (DateTime(tz), server_default=now())
  - `updated_by` (String(255), nullable)

### backend/app/schemas/schemas.py (extend)

#### Alert type enum
```python
class AlertType(str, Enum):
    stale_pr = "stale_pr"
    review_bottleneck = "review_bottleneck"
    underutilized = "underutilized"
    uneven_assignment = "uneven_assignment"
    merged_without_approval = "merged_without_approval"
    revert_spike = "revert_spike"
    high_risk_pr = "high_risk_pr"
    bus_factor = "bus_factor"
    team_silo = "team_silo"
    isolated_developer = "isolated_developer"
    declining_trend = "declining_trend"
    issue_linkage = "issue_linkage"
    ai_budget = "ai_budget"
    sync_failure = "sync_failure"
    unassigned_roles = "unassigned_roles"
    missing_config = "missing_config"
```

#### Notification response schemas
```python
class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    alert_type: str
    severity: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: int | None
    link_path: str | None
    developer_id: int | None
    metadata: dict | None
    is_read: bool = False
    is_dismissed: bool = False
    created_at: datetime
    updated_at: datetime

class NotificationsListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
    counts_by_severity: dict[str, int]  # {"critical": 2, "warning": 3, "info": 1}
    total: int
```

#### Dismiss schemas
```python
class DismissNotificationRequest(BaseModel):
    dismiss_type: Literal["permanent", "temporary"] = "permanent"
    duration_days: int | None = None  # for temporary — creates expires_at

class DismissAlertTypeRequest(BaseModel):
    alert_type: str
    dismiss_type: Literal["permanent", "temporary"] = "permanent"
    duration_days: int | None = None
```

#### Config schemas
```python
class NotificationConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # All toggle + threshold fields from NotificationConfig model
    # Plus computed field:
    alert_types: list[dict]  # [{key, label, description, enabled, thresholds: [...]}]

class NotificationConfigUpdate(BaseModel):
    # All fields optional for PATCH semantics
    alert_stale_pr_enabled: bool | None = None
    stale_pr_threshold_hours: int | None = None
    # ... (one optional field per config column)
    exclude_contribution_categories: list[str] | None = None
    evaluation_interval_minutes: int | None = None
```

### Alembic migration
- Single migration creating all 4 tables + indexes + unique constraints
- Seed `NotificationConfig` singleton row (id=1) with all defaults
- Note: no prod data exists (per project memory), so simple CREATE TABLE is fine

### Design Notes
- `alert_key` uniqueness enables upsert pattern: if condition still active, update `updated_at`; if new, insert
- `resolved_at` enables auto-cleanup: evaluation sets this when condition clears, query filters `resolved_at IS NULL` for active alerts
- `NotificationRead` is intentionally separate from `NotificationDismissal` — reading clears the badge count, dismissing hides the notification
- Expired temporary dismissals (now > expires_at) are treated as non-dismissed at query time
- The `metadata` JSONB is for UI enrichment only (e.g. risk factors list, threshold that was exceeded) — never queried for alert logic
