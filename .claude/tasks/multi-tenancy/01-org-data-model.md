# Phase 01: Org data model + tenancy migration

**Status:** Planned
**Priority:** High
**Type:** infrastructure
**Apps:** devpulse
**Effort:** large
**Parent:** multi-tenancy/00-overview.md

## Scope

Introduce the `organizations` table and stamp `org_id` on every data-carrying table in DevPulse. This is the foundation every subsequent phase builds on — no auth, sync, or query can be tenant-scoped until the schema knows what a tenant is.

## What "done" looks like

- An `organizations` table exists with `id`, `name`, `slug` (url-safe, unique), `created_at`, `status` (`active` / `suspended` / `trial`), `tier` (placeholder for Phase 04)
- Every table that holds customer data carries `org_id` FK with `ON DELETE CASCADE` and a non-null constraint (after migration)
- A single Alembic migration handles: create `organizations`, insert a "default" org, add nullable `org_id` columns, backfill all rows to the default org, then flip `org_id` to `NOT NULL`
- Model-layer scope helpers: `query.filter_by_org(org)` extension or equivalent pattern that every service can use consistently
- Running tests + current app functionality continue to work unchanged (default org is implicit in all single-tenant flows)

## Tables that need `org_id`

Audit of `backend/app/models/models.py` (39 tables). Most carry customer data; a few are truly global. Rough cut — Phase 01 validates the exact list:

**Needs `org_id` (customer data):**
- `developers`, `role_definitions`, `developer_identity_map`
- `repositories`, `pull_requests`, `reviews`, `review_comments`, `pr_comments`
- `issues`, `external_issues`, `external_projects`, `external_cycles`, `pr_external_issue_links`
- `commits`, `code_changes`
- `mentions`, `co_authors`, `collaboration_scores`
- `work_categorization_rules`, `work_categorizations`
- `integration_config`, `sync_schedule_config`, `sync_events`
- `ai_analyses`, `ai_feature_toggles`, `ai_budget_config`, `ai_usage_log`
- `notifications`, `notification_preferences`, `alert_thresholds`
- `goals`, `goal_progress`
- `one_on_ones`, `team_health_reports`

**Stays global (platform-level):**
- `alembic_version` (Alembic internal)
- `super_admins` (new in Phase 07 — platform, not tenant)
- Rate-limit tracking (if any stored in DB — currently in Redis, so N/A)

## Key design decisions

- **Single schema, row-level scoping** — not separate schemas per tenant (Postgres can't scale `CREATE SCHEMA` to hundreds of tenants cleanly, backups become painful, migrations run N times)
- **`org_id` is always the leading column of composite indexes** on hot query paths (Phase 05 hardens this; Phase 01 just adds the column)
- **`ON DELETE CASCADE`** from `organizations` — suspending an org is a soft operation (`status='suspended'`), but hard-deleting an org removes all of its data deterministically
- **Slug is user-facing**, id is internal. Slug used in URLs (`/o/:slug/...`) is deferred to Phase 06 but we reserve the column now.
- **No `tenant_id` alias** — stick with `org_id` everywhere for consistency with Claros's existing convention.

## Checklist

- [ ] Audit `models.py` — confirm the tenant/global split above, update the list if any tables were missed
- [ ] Add `Organization` model to `models.py` with `id`, `name`, `slug` (unique index), `status`, `tier`, `created_at`, `deleted_at` (for soft-delete later)
- [ ] Write Alembic migration:
  - Create `organizations` table
  - `INSERT INTO organizations (id, name, slug, status, tier) VALUES (1, 'Default', 'default', 'active', 'internal')`
  - For each tenant-scoped table: `ADD COLUMN org_id INTEGER`, `UPDATE ... SET org_id=1`, `ALTER COLUMN org_id SET NOT NULL`, `ADD FOREIGN KEY`
  - Sanity-check row counts before + after
- [ ] Add ORM-level helper: `def scoped(cls, org_id: int)` or `OrgScopedQuery` mixin — whichever pattern feels most natural in this codebase
- [ ] Add `org_id` to every relevant `__table_args__` index tuple (the old indexes stay for now; Phase 05 adds the composite ones)
- [ ] Update fixtures in `backend/tests/conftest.py` to create a default test org and stamp it on all factory-created rows
- [ ] Run full test suite locally — all existing tests must pass with the migration applied
- [ ] Document the migration in `docs/architecture/DATA-MODEL.md` under a new "Multi-tenancy" section
- [ ] `/architect data-model` to regenerate architecture docs after the model change lands

## Risks

- **Forgotten table** — if any customer-data table ships without `org_id`, Phase 02 will leak data cross-tenant. Mitigation: `/code-reviewer` pass on the migration specifically looking for missed tables, plus an E2E test in Phase 02 that asserts isolation.
- **Migration speed** — on a small DB (DevPulse is pre-prod) this is trivial. If/when prod has data, the `ALTER COLUMN ... NOT NULL` can take minutes on large tables; plan with Postgres `SET STATEMENT_TIMEOUT` awareness.
- **ORM relationship cascading** — SQLAlchemy relationships that don't carry `org_id` in the join condition can accidentally cross tenants. All relationships involving tenant tables should include `primaryjoin=and_(..., OrgModel.org_id==OtherModel.org_id)` — OR enforce at the service/query layer only. Decide the pattern and apply consistently.

## Out of scope (handled by later phases)

- Scoping queries in services — Phase 02
- JWT carrying `org_id` — Phase 02
- Composite indexes on `(org_id, ...)` — Phase 05
- Data-isolation E2E test — Phase 02 (needs auth to create a real test)
