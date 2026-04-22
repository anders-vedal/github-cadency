# Phase 02: Org-scoped auth + access

**Status:** Planned
**Priority:** High
**Type:** security
**Apps:** devpulse
**Effort:** large
**Parent:** multi-tenancy/00-overview.md
**Dependencies:** multi-tenancy/01-org-data-model.md

## Scope

Thread `org_id` through authentication, authorization, and every query in DevPulse. Bind the GitHub App installation and Linear workspace to a specific org. Make cross-org access impossible at the service layer. This is the load-bearing security phase — get it wrong and tenants see each other's data.

## What "done" looks like

- JWTs carry `org_id` as a first-class claim. `AuthUser` exposes `org_id` and `org_slug`.
- Every service function that takes `db: AsyncSession` also takes (or derives) `org_id` and filters on it. No service query touches another org's rows.
- `get_current_user()` resolves `org_id` from the JWT. `require_admin()` becomes "admin **within this org**".
- A new GitHub App install prompts the user to **bind it to a specific org** (their existing one, or create a new one). Same for Linear workspaces.
- Attempting to access another org's resource (by ID guess) returns 404, not 403 (avoid enumeration leaks).
- An integration test asserts cross-org isolation for every API router: seed two orgs with distinct data, request org A's resources with org B's token, confirm 404 on every detail endpoint and empty list on every list endpoint.

## Key design decisions

- **JWT claim**: `{ "sub": user_id, "org_id": 42, "org_slug": "acme", "role": "admin", "token_version": 3 }`. Token version invalidates on org-role change or user deactivation (existing pattern).
- **Request-time scope**: rather than passing `org_id` as a function arg everywhere, inject it via a FastAPI dependency and attach to `request.state.org_id`. Services accept `org_id` as an explicit param though — the request-scoped value is only for the router layer. Explicit > magic for security-sensitive code.
- **Cross-org resource access**: 404 on detail endpoints (deny existence), empty list on collection endpoints. Never 403 — a 403 confirms the resource exists.
- **GitHub App install → org binding**: store in a new `github_installations` table (`install_id`, `org_id`, `installed_by_user_id`, `installed_at`). The install webhook consults this table; if the install doesn't map to an org yet, it's held in a pending state and surfaced in the onboarding UI. Deferred onboarding UX is Phase 06's job; Phase 02 just sets up the data structure and the "pending install → claim flow" API.
- **Linear workspace → org binding**: `integration_config` already exists but today is global. Move it to org-scoped (already happens in Phase 01). Phase 02 adds the "workspace already claimed by another org" rejection path — an API key for a workspace that's already bound returns a specific error telling the user to contact support (rare, but prevents silent cross-tenant linkage).
- **Structlog**: add `org_id` to the LoggingContextMiddleware so every log line in a tenant request carries it.

## Checklist

### JWT + auth core
- [ ] Extend JWT payload with `org_id` and `org_slug`
- [ ] `AuthUser` dataclass gains `org_id`, `org_slug`
- [ ] `get_current_user()` pulls `org_id` from JWT and validates user still belongs to that org (defense against org removal not invalidating tokens)
- [ ] `require_admin()` checks user's role **within the JWT's org_id** (not globally)
- [ ] `LoggingContextMiddleware` adds `org_id` to context

### Service layer scoping
- [ ] Every service function that reads/writes tenant-scoped tables takes `org_id: int` as its first positional arg (or second, after `db`)
- [ ] Every `select(...)` in those functions filters on `Model.org_id == org_id`
- [ ] Every `insert(...)` / model instantiation sets `org_id`
- [ ] Code review pass explicitly for "query that doesn't filter by org_id" — this is the security-critical audit

### Router layer
- [ ] `OrgScope` FastAPI dependency that resolves `org_id` from `AuthUser` and injects into `request.state`
- [ ] Every router pulls `org_id` from `request.state` (or takes `OrgScope` as a Depends) and passes into service calls
- [ ] Detail endpoints return 404 on cross-org access (not 403)
- [ ] List endpoints are implicitly scoped — no extra work needed if the service layer is correct

### GitHub App install binding
- [ ] New table `github_installations` (`install_id` unique, `org_id` FK, `installed_by_user_id`, `installed_at`, `status`)
- [ ] GitHub App `installation.created` webhook handler: if install not yet bound, create pending row + emit event for Phase 06 UI to claim
- [ ] `POST /api/integrations/github/claim` — authenticated endpoint that binds a pending install to the caller's org (with a check that the caller is an admin of the install's GitHub org or account)
- [ ] `GET /api/integrations/github/installations` — lists installs for current org
- [ ] Sync service reads installation ID from `github_installations` table, not from global config

### Linear workspace binding
- [ ] `integration_config` unique constraint: `(org_id, type)` — one Linear config per org
- [ ] "Workspace already claimed" rejection path when attempting to save a Linear API key whose workspace ID is already bound to another org
- [ ] Sync service reads Linear API key from `integration_config` scoped to current org

### Testing
- [ ] Cross-org isolation integration test: seed 2 orgs with distinct developers/repos/issues, make a request from org A's user for org B's resource by ID, assert 404. Cover every detail endpoint (~50+ routes).
- [ ] List-scope test: list endpoints return only the caller's org's rows.
- [ ] JWT-org mismatch test: forging `org_id` claim (user belongs to org X, JWT says org Y) → 401 on validation.
- [ ] Webhook cross-tenant test: GitHub webhook payload for install bound to org A is processed against org A's data only, even if repo IDs happen to collide with org B.

## Risks

- **Forgotten service** — if one service module doesn't scope queries, data leaks. Mitigation: a lint rule or grep check that every `.execute(select(` in `services/` appears within N lines of a `.filter(...org_id==` or equivalent. Imperfect but catches most cases. The integration test is the final backstop.
- **Webhook replay attacks** — a malicious actor with a replayed GitHub webhook could theoretically trigger sync actions against the wrong org if the install→org binding isn't checked. Every webhook handler must resolve org from the install_id, not from any payload-provided field.
- **Existing single-user token compat** — current JWTs don't have `org_id`. Migration path: after deploy, all existing tokens get rejected (force re-login) — acceptable because DevPulse isn't in prod yet. Flag in the deploy checklist.

## Out of scope (later phases)

- Sync worker changes (Phase 03 replaces in-process scheduler; this phase keeps APScheduler but makes it org-aware)
- Quota enforcement (Phase 04)
- Public signup UX (Phase 06 — this phase only adds the "pending install claim" backend)
- Super-admin cross-org access (Phase 07 adds `super_admin` bypass for ops routes)
