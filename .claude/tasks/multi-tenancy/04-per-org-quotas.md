# Phase 04: Per-org quotas + rate limits

**Status:** Planned
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** multi-tenancy/00-overview.md
**Dependencies:** multi-tenancy/02-org-scoped-auth.md

## Scope

Prevent one noisy tenant from consuming the whole server. Introduce tiers, per-tier quotas (repo count, min sync interval, AI monthly budget, API rate limits), and enforcement middleware. At MVP, one free tier with conservative defaults — no Stripe, no paid plans. The tier table is future-proofed so Stripe integration is a follow-up epic, not a refactor.

## What "done" looks like

- A `tiers` table defines quota limits; each `organizations.tier` points at a row
- Default "free" tier: max 10 repos, min 60-min sync interval, $10/month AI budget, 60 req/min API rate limit, 1 concurrent sync
- Quota enforcement fires at the right layer: API returns 402/429 when quota exceeded, worker gracefully refuses to enqueue (for concurrency and sync interval)
- slowapi rate limit keys switch from global to per-org
- AI guards (existing `AIFeatureDisabledError`, `AIBudgetExceededError`) become per-org
- Super-admin can override a tenant's tier without a deploy (Phase 07 exposes the UI; this phase ships the API)

## Key design decisions

- **Tier as a row, not an enum**: `tiers` table with columns `name`, `max_repos`, `min_sync_interval_minutes`, `max_concurrent_syncs`, `ai_monthly_budget_usd`, `api_rate_limit_per_min`. Change tier values with a SQL update, no code deploy. Adding a new tier = one INSERT.
- **Quota enforcement returns real HTTP codes**:
  - `402 Payment Required` — you're past a hard quota (repo count, AI budget), user-actionable
  - `429 Too Many Requests` — transient, retry later (rate limit, concurrent sync cap)
  - `403 Forbidden` — only for permission denials, not quotas
- **Rate limit by org, not user**: slowapi's `key_func` becomes `lambda request: request.state.org_id`. Users within an org share the bucket (prevents a single user DoS, but also doesn't let a 10-user org legitimately get 10× more throughput than a 1-user org — that's fine for MVP).
- **AI budget enforcement**: existing `ai_budget_config` table becomes per-org (Phase 01 migration handles this). Budget check at the AI call site, not in middleware — too coarse otherwise.
- **Super-admin bypass**: requests with `X-Admin-Override: true` + super-admin JWT bypass quotas, for ops triage (logged with a loud audit event).
- **No overage charges**: free tier hits the ceiling → user sees a friendly "upgrade" message in UI. No auto-charge, no throttling that silently misbehaves. Clean denial.

## Checklist

### Schema
- [ ] Alembic migration: create `tiers` table with columns above, insert `free` row with default values
- [ ] `organizations.tier` FK to `tiers.name` (string FK — easier than id lookups in code)
- [ ] Seed all existing orgs to `tier='free'`

### Quota service
- [ ] `backend/app/services/quotas.py` — one function per quota check, e.g. `enforce_repo_quota(db, org_id)`, `enforce_sync_interval(db, org_id, sync_type)`, etc.
- [ ] Cache the tier row per-org in memory for 60s (avoid hitting DB on every request)

### Enforcement call sites
- [ ] `POST /api/repositories` (add repo) → `enforce_repo_quota` before insert
- [ ] `POST /api/sync/trigger` → `enforce_sync_interval` (reject if last successful sync < min_interval ago) + `enforce_concurrent_sync_limit`
- [ ] Scheduler tick in worker → same interval check before enqueue
- [ ] AI call sites → `enforce_ai_budget(db, org_id, estimated_cost_usd)` before `ProviderRouter.call()`
- [ ] Global middleware → slowapi keyed by `request.state.org_id`

### Frontend
- [ ] When API returns 402 with `quota_exceeded` body, show inline upgrade CTA (placeholder "contact us" for MVP — Phase 06 signup UX refines this)
- [ ] "Usage" card on org settings page showing repos used / limit, AI spend this month / limit, sync frequency

### Super-admin ops
- [ ] `PATCH /api/admin/orgs/{org_id}/tier` — super-admin-only endpoint to change tier (logged, audit event)
- [ ] `POST /api/admin/orgs/{org_id}/quota-override` — time-bounded override (e.g. "give acme 30 repos for the next 30 days")

### Observability
- [ ] structlog events `quota.exceeded` (warn) and `quota.override` (info) — both carry `org_id`, `quota_type`, `limit`, `current_value`
- [ ] Sentinel gets alerted on `quota.override` as a trail (audit, not error)

### Testing
- [ ] Unit test: org at 10 repos → 402 on 11th add
- [ ] Unit test: org hits AI budget → subsequent AI call raises `AIBudgetExceededError`
- [ ] Integration test: 2 orgs, one hammering API at 200 req/min — other org's 60 req/min still works (rate limit is correctly isolated)
- [ ] Unit test: super-admin override bypasses quota, emits audit event

## Risks

- **Quota check race conditions**: "11 concurrent requests to add repo 10" could all pass the check and insert 11. Mitigation: unique constraint + SELECT count inside a transaction, OR a Postgres check constraint / DB-level row count trigger. Low risk in practice because admins don't usually hammer the repo-add endpoint, but worth a unit test.
- **Tier cache staleness**: changing a tier (e.g. upgrading acme to paid) takes up to 60s to propagate. Acceptable trade-off for the DB load reduction. If it becomes painful, invalidate cache on `PATCH /api/admin/orgs/{org_id}/tier`.
- **AI budget granularity**: billed in post-call dollars, so the budget check before a call is an estimate. A single expensive call could go slightly over budget. Mitigation: check-then-call pattern with a small buffer (reject when usage > 95% of budget). Refined by Phase 07's per-org spend visibility.

## Out of scope (later phases)

- Stripe billing (future epic)
- Self-serve tier upgrade UI (future epic — MVP sticks to free tier, upgrades happen via super-admin or manual support request)
- Multi-user rate limit (per-user within org) — not needed for MVP, org-level limit is enough
