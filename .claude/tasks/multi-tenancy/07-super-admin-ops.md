# Phase 07: Super-admin ops dashboard

**Status:** Planned
**Priority:** Medium
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** multi-tenancy/00-overview.md
**Dependencies:** multi-tenancy/03-sync-worker-extraction.md, multi-tenancy/04-per-org-quotas.md

## Scope

The ops-facing counterpart to the customer-facing app. A "super-admin" (platform operator, not a tenant admin) sees every org, their usage, their AI spend, their sync health, and can take ops actions: suspend a misbehaving org, change a tier, trigger a manual sync, reset quotas, see sync worker health. This is the view Anders uses to keep the lights on for 20–50 tenants without SSHing into the server.

## What "done" looks like

- `/admin/ops` route (separate from per-org admin routes), accessible only to super-admins
- Org list: name, tier, created_at, repo count, last sync, AI spend this month, status. Sortable, filterable.
- Org detail page: full usage breakdown, sync history, billing events (placeholder until Stripe), support notes
- Actions: suspend/resume org, change tier, override a quota (time-bounded), trigger sync, reset AI budget, impersonate user (for support troubleshooting)
- Worker health: queue depth, in-flight jobs, failed jobs in last 24h, per-org sync success rate
- Sentinel integration: each error aggregate shows which org it came from, drill-through link
- Abuse signals: orgs with unusual patterns (sync failure spikes, repeated quota overrides, signup→abandon rate, API error ratio) flagged for review

## Key design decisions

- **Super-admin is a platform role, not a tenant role**: enforced via a separate `super_admins` table (user_id + added_at + added_by). Not a flag on `developers` — keeps tenant user data cleanly separated from platform roles.
- **Initial bootstrap**: env var `DEVPULSE_SUPER_ADMINS=anders-vedal` — comma-separated GitHub logins. On first login, matching users are auto-inserted into `super_admins`. After first super-admin exists, they can invite others via the admin UI and the env var becomes vestigial.
- **Impersonation**: super-admin can mint a short-lived (15 min) JWT scoped to a target org, flagged as `impersonation=true`, which logs loudly on every request. Used for "I can't see what the customer sees" support moments.
- **Suspension semantics**: `organizations.status='suspended'` — users see a maintenance page on login, syncs are skipped by the worker, AI calls 402, but data is preserved. Un-suspending restores everything. Different from `deleted_at` (soft-delete, hard to reverse) and from tier downgrade (still active, lower limits).
- **Cost/usage rollups**: AI spend is already tracked per-call in `ai_usage_log`; roll up nightly into `org_monthly_usage` for fast dashboard queries. Sync duration totals similarly. Keep raw logs 90 days.
- **Sentinel org tagging**: extend the existing `ErrorReporter` to include `org_id` in the report payload — Sentinel can then group errors by tenant. Coordinate with Sentinel's schema if needed.

## Checklist

### Schema
- [ ] `super_admins` table: `user_id` PK, `added_at`, `added_by_user_id`, `notes`
- [ ] `org_monthly_usage` rollup table: `org_id`, `month`, `ai_spend_usd`, `sync_seconds_total`, `repo_count`, `pr_count`, `active_users`
- [ ] `org_support_notes` table: free-form notes super-admins can attach to an org

### Backend
- [ ] `is_super_admin(user_id) -> bool` helper and FastAPI dependency `require_super_admin()`
- [ ] Auto-populate super-admins from env var on app startup
- [ ] `GET /api/admin/orgs` — paginated list with usage columns
- [ ] `GET /api/admin/orgs/{org_id}` — full detail
- [ ] `PATCH /api/admin/orgs/{org_id}` — status, tier, notes (audit-logged)
- [ ] `POST /api/admin/orgs/{org_id}/impersonate` — returns short-lived JWT for that org
- [ ] `POST /api/admin/orgs/{org_id}/sync-trigger` — enqueue a sync
- [ ] `GET /api/admin/worker/health` — queue depth, in-flight, failed recent
- [ ] `GET /api/admin/abuse-signals` — orgs flagged by the abuse detector
- [ ] Nightly worker job: roll up `org_monthly_usage` from `ai_usage_log` + `sync_events`

### Frontend
- [ ] `/admin/ops` layout (distinct from per-org `/admin/*` routes) — different color scheme (amber border?) to make "you're in ops mode" unmistakable
- [ ] Orgs list page with filter/sort
- [ ] Org detail page with action buttons + confirmation dialogs
- [ ] Worker health dashboard card (auto-refresh every 30s)
- [ ] Abuse signals page
- [ ] Impersonation banner (red bar at top) when `impersonation=true` JWT is active

### Observability
- [ ] structlog events: `admin.org.suspended`, `admin.org.tier_changed`, `admin.org.impersonation_started`, `admin.org.impersonation_ended`, all with `target_org_id`, `acting_super_admin_id`
- [ ] Extend `ErrorReporter` to include `org_id` in Sentinel reports
- [ ] Add "filter by org_id" saved views to Sentinel project (one-time setup)

### Abuse signals (simple rules, not ML)
- [ ] Sync failure rate > 50% in last 24h → flag
- [ ] Quota overrides > 3 in last 30 days → flag
- [ ] API 4xx error ratio > 20% in last hour → flag
- [ ] Signup + no integration + no login for 7 days → flag for cleanup review
- [ ] AI spend > 90% of budget with > 5 days left in month → flag (user should know)

### Testing
- [ ] Unit: non-super-admin user hits `/api/admin/*` → 404 (not 403)
- [ ] Integration: super-admin suspends org X; user of org X gets 403 on data routes but org Y still works
- [ ] Integration: impersonation JWT scoped to org X can't access org Y
- [ ] Audit-log test: every admin action emits the expected structlog event with correct fields

## Risks

- **Privileged actions need extra-loud audit trails** — accidental suspension of a real customer because of a mis-click is embarrassing. Confirmation dialogs with "type the org slug to confirm" for suspend + tier change. Two-person approval (later phase) if it becomes a real risk.
- **Impersonation is a foot-gun** — any edit action during impersonation will appear as the target org's own edit. Mitigation: impersonation JWTs are **read-only** by default; super-admin must explicitly request write-scope ("I need to clean up a broken sync config"), which triggers an extra warning + audit event. Write-scope tokens are 5 min, not 15.
- **Multi-org users and UI confusion**: if signup flow (Phase 06) later adds multi-org per user, the super-admin's own UI needs to clearly separate "my tenant view" from "my ops view" — handled by the distinct `/admin/ops` route + visual styling.

## Out of scope (later phases)

- Billing / invoicing ops views — future Stripe epic
- Customer support ticket integration — future epic
- Fine-grained super-admin roles (read-only ops vs. write ops) — start with one role, split if it becomes necessary
- Automated anomaly detection beyond simple rule-based flags — future data-science epic if/when it matters
