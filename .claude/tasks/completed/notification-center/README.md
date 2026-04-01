# Notification Center v2

Unified alert system replacing the current unbounded AlertStrip stacking with a materialized notification center: bell icon in header, server-side persistence, read/dismiss tracking, auto-resolution, and admin-configurable thresholds with contribution_category filtering.

## Tasks

| Task | Title | Status | Depends On |
|------|-------|--------|------------|
| NC-01 | Database models + migration | pending | — |
| NC-02 | Alert evaluation service | pending | NC-01 |
| NC-03 | API endpoints | pending | NC-01, NC-02 |
| NC-04 | Frontend notification center | pending | NC-03 |

## Key Design Decisions

- **Materialized alerts**: Background evaluator writes to `notifications` table (not computed on every page load)
- **Auto-resolution**: When conditions clear, `resolved_at` is set — notification disappears
- **Contribution_category filtering**: System/non-contributor roles excluded from activity alerts at evaluation time
- **Read vs Dismiss**: Reading clears the badge, dismissing hides the notification (two separate tables)
- **Type-level dismiss**: "Mute all underutilized alerts for 7 days"
- **Admin-configurable**: Every threshold and alert type has an enable toggle + configurable parameters
- **Supersedes**: `improvements/P3-09-configurable-alert-thresholds.md`

## Alert Types (16)

stale_pr, review_bottleneck, underutilized, uneven_assignment, merged_without_approval, revert_spike, high_risk_pr, bus_factor, team_silo, isolated_developer, declining_trend, issue_linkage, ai_budget, sync_failure, unassigned_roles, missing_config
