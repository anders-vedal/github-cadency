# Architectural Concerns

Tasks derived from the `/architect` full audit on 2026-03-29. Organized by severity (H = High, M = Medium, L = Low) and area.

## Task Index

### High Severity
- [H-01](H-01-missing-initial-migration.md) — Add initial schema migration
- [H-02](H-02-jwt-revocation.md) — Add JWT revocation for deactivated users
- [H-03](H-03-sync-httpx-import-bug.md) — Fix missing `httpx` import in sync.py

### Medium Severity — Data Layer
- [M-01](M-01-missing-database-indexes.md) — Add missing database indexes
- [M-02](M-02-github-id-uniqueness.md) — Add unique constraints on `github_id` columns
- [M-03](M-03-repo-ids-json-jsonb-drift.md) — Fix `repo_ids` JSON vs JSONB schema drift

### Medium Severity — Backend
- [M-04](M-04-webhook-approval-metrics.md) — Call `compute_approval_metrics()` in webhook review handler
- [M-05](M-05-collaboration-scores-date-range.md) — Fix collaboration scores 30-day window
- [M-06](M-06-claude-api-retry.md) — Add retry/timeout to Claude API calls
- [M-07](M-07-service-http-exceptions.md) — Remove HTTPException from service layer
- [M-08](M-08-stats-n-plus-1.md) — Fix N+1 query pattern in benchmarks
- [M-09](M-09-sync-toctou-race.md) — Add DB-level locking for sync concurrency

### Medium Severity — Frontend
- [M-10](M-10-single-error-boundary.md) — Add per-section error boundaries
- [M-11](M-11-lazy-loading.md) — Add React.lazy route-level code splitting
- [M-12](M-12-duplicated-components.md) — Extract shared AlertStrip/SortableHead components
- [M-13](M-13-ci-stats-repo-filter-bug.md) — Fix `useCIStats` broken `repoId` parameter
- [M-14](M-14-cost-estimate-usestate-bug.md) — Fix `CostEstimateLine` useState side effect

### Low Severity
- [L-01](L-01-default-range-duplication.md) — Extract shared `_default_range()` utility
- [L-02](L-02-python-only-defaults.md) — Add `server_default` to non-nullable columns
- [L-03](L-03-dead-code-cleanup.md) — Remove dead code and orphaned files
- [L-04](L-04-native-select-consistency.md) — Replace native `<select>` with shadcn Select
- [L-05](L-05-orm-missing-relationships.md) — Add missing ORM relationships
- [L-06](L-06-type-annotation-fixes.md) — Fix ORM type annotation mismatches
