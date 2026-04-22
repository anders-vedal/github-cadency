# Phase 05: Query performance hardening

**Status:** Planned
**Priority:** Medium
**Type:** tech-debt
**Apps:** devpulse
**Effort:** medium
**Parent:** multi-tenancy/00-overview.md
**Dependencies:** multi-tenancy/01-org-data-model.md

## Scope

Keep query latency flat as the DB grows from one tenant to dozens. Add composite `(org_id, ...)` indexes on every hot path, audit for N+1 queries, tune the asyncpg pool, deploy PgBouncer in prod. This phase can start after Phase 01 but is best polished after Phase 02 (you want real per-org queries to profile against).

## What "done" looks like

- Every hot query has a matching composite index starting with `org_id`
- No list endpoint emits N+1 queries (spot-checked on the biggest endpoints: dashboard, workload, collaboration, sync history)
- Postgres connection pool tuned (SQLAlchemy `pool_size`, `max_overflow`)
- PgBouncer in front of Postgres in prod compose (transaction mode, 200 max clients)
- Load test: 50 seeded orgs on staging, simulated read traffic across all of them, p95 < 500ms on every route in the Insights section

## Key design decisions

- **Composite index leading with `org_id`**: `(org_id, created_at DESC)` not `(created_at, org_id)`. All our queries filter by org first, so `org_id` leads. The old single-column indexes can stay (Postgres won't use them for scoped queries, but they don't cost much).
- **Don't over-index on write-heavy tables**: `pr_comments`, `reviews` see a lot of inserts during sync. Add only the indexes we actually measure as needed, not every theoretical composite.
- **N+1 audit via echo=True + eyeballs**: turn on SQLAlchemy query logging for a few representative requests, count DISTINCT SQL statements. Anything with > 1 query per logical list item is a target for `.selectinload()` or a single JOINed query.
- **asyncpg pool sizing**: with N workers at M pool_size each, total connections = N × M. Target 50 orgs × 5 avg-concurrent-req × slack factor = needs ~50 connections from API + ~20 from worker. PgBouncer in transaction mode lets us use 200 client-side connections against a Postgres max_connections of 50–75. Saves prod dollars.
- **Materialized views**: skip for MVP — the biggest slow queries are on `collaboration_scores` which is already materialized (computed post-sync). Revisit if team-benchmark or DORA queries get slow.

## Checklist

### Indexes
- [ ] Audit all models' `__table_args__` for existing single-column indexes on tenant-scoped tables
- [ ] Add composite `(org_id, <common-filter>)` indexes for each:
  - `pull_requests`: `(org_id, created_at)`, `(org_id, closed_at)`, `(org_id, author_id)`, `(org_id, repo_id)`
  - `reviews`: `(org_id, submitted_at)`, `(org_id, reviewer_id)`
  - `issues`: `(org_id, created_at)`, `(org_id, closed_at)`, `(org_id, repo_id)`
  - `external_issues`: `(org_id, created_at)`, `(org_id, assignee_id)`
  - `pr_comments`: `(org_id, created_at)`, `(org_id, pr_id)`
  - `notifications`: `(org_id, created_at)`, `(org_id, user_id, read_at)`
  - `sync_events`: `(org_id, started_at)`
  - `ai_usage_log`: `(org_id, created_at)`
- [ ] One Alembic migration adds them all, `CONCURRENTLY` if non-trivial data volumes
- [ ] Verify via `EXPLAIN ANALYZE` on representative queries that the new indexes are chosen

### N+1 audit
- [ ] Enable `echo=True` on SQLAlchemy engine for a dev-only debugging session
- [ ] Hit each Insights page once, capture statements per request
- [ ] Fix the offenders: `selectinload`, `joinedload`, or a single explicit JOIN
- [ ] Re-run, confirm query count is bounded (e.g. dashboard = 3–5 queries, not 50+)

### Pool + connection
- [ ] Raise `pool_size` to 10, `max_overflow` to 20 in SQLAlchemy engine config
- [ ] Add PgBouncer to `docker-compose.yml` (prod) in transaction mode, 200 max clients, pointed at Postgres
- [ ] Update `DATABASE_URL` to hit PgBouncer port 6432
- [ ] Verify Alembic still connects directly to Postgres (not PgBouncer — Alembic uses prepared statements which don't work in transaction mode)

### Testing / validation
- [ ] Local: seed 50 test orgs with realistic-volume data (use sync of a public repo like kubernetes/kubernetes scaled-down)
- [ ] Load test with `locust` or `hey`: 50 concurrent users, mixed read traffic, 5-minute duration
- [ ] Assert p95 < 500ms on `/api/dashboard`, `/api/insights/workload`, `/api/insights/collaboration`, `/api/sync/history`
- [ ] Document results in `docs/architecture/PERFORMANCE.md` (new file) with baseline numbers

## Risks

- **Index bloat**: adding 20+ composite indexes doubles write amplification on tenant tables. For MVP scale, negligible. Watch index size in Phase 07 admin dashboard.
- **PgBouncer + SQLAlchemy prepared statements**: asyncpg uses named prepared statements by default, which break in PgBouncer transaction mode. Must set `statement_cache_size=0` or use `server_side_cursors=False`. Test explicitly.
- **`CREATE INDEX CONCURRENTLY` failure**: can't run inside a transaction. Requires running outside Alembic's default transaction wrapper — use `op.execute()` with `autocommit=True` or a separate migration script. Low-risk to miss; if the index fails to build, migration fails loudly.

## Out of scope (later phases)

- Horizontal sharding / read replicas — well past MVP capacity
- Denormalized aggregates for dashboard load — only if we measure it as a problem
- Query result caching (Redis-backed) — revisit when AI analysis views get heavy
