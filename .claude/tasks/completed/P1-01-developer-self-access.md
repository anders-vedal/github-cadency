# Task P1-01: Developer Self-Access Tokens

## Phase
Phase 1 — Make It Usable

## Status
completed

## Blocked By
- 02-sqlalchemy-models

## Blocks
- P1-03-developer-self-goals

## Description
Add per-developer read-only authentication so developers can view their own stats, trends, and goals without the admin token. This is the single most important structural change — it transforms DevPulse from a surveillance tool into a self-service platform.

Currently every endpoint requires `DEVPULSE_ADMIN_TOKEN`. Developers cannot access the tool at all.

## Deliverables

### Database migration
Add column to `developers`:
- `personal_token` (UUID, unique, not null, default generated) — read-only access token scoped to the developer's own data

Create Alembic migration. Generate a UUID for each existing developer row.

### backend/app/api/auth.py (extend)
Add a secondary auth path alongside the existing admin token:
- If `Authorization: Bearer {token}` matches `DEVPULSE_ADMIN_TOKEN` → full access (existing behavior)
- If token matches a `developers.personal_token` → resolve `developer_id`, set a request-scoped context variable
- New dependency: `get_current_developer() -> Optional[int]` returning the authenticated developer's ID or None for admin

### backend/app/api/stats.py (extend)
When authenticated as a developer (not admin):
- `GET /api/stats/developer/{id}` — only allow if `{id}` matches authenticated developer
- `GET /api/stats/developer/{id}/trends` — same restriction
- Block access to `GET /api/stats/team`, `GET /api/stats/workload`, `GET /api/stats/collaboration`, `GET /api/stats/benchmarks`

### backend/app/api/developers.py (extend)
- `GET /api/developers/{id}` — allow if ID matches authenticated developer (read-only)
- Block `POST`, `PATCH`, `DELETE` for developer tokens

### backend/app/api/goals.py (extend)
When authenticated as a developer:
- `GET /api/goals?developer_id={own_id}` — allow
- `GET /api/goals/{id}/progress` — allow if goal belongs to own developer_id
- Block creation/modification (see P1-03 for self-goal creation)

### Frontend: Token entry UI
- Add a simple login page at `/login` as the default route when no token is in localStorage
- Input field for pasting either admin token or personal developer token
- On submit, store in localStorage and redirect to Dashboard (admin) or personal detail page (developer)
- Show "Invalid token" error on 401 response

## Implementation Notes (Completed 2026-03-28)

**Deviated from original spec:** Used GitHub OAuth instead of personal UUID tokens per user request. This provides better UX (no token distribution needed) and leverages the existing GitHub App infrastructure.

### What was implemented:
- **GitHub OAuth** login flow (`GET /api/auth/login`, `GET /api/auth/callback`, `GET /api/auth/me`)
- **JWT sessions** (7-day expiry) replacing the single `DEVPULSE_ADMIN_TOKEN`
- **Role-based access control** with `app_role` column on `developers` table (`admin` | `developer`)
- **Bootstrap:** `DEVPULSE_INITIAL_ADMIN` env var auto-promotes first matching GitHub user to admin
- **Admin promotion UI:** Admins can promote/demote via `PATCH /api/developers/{id}` with `app_role` field
- **Frontend:** Login page, OAuth callback handler, AuthContext, role-aware nav and routing
- **Security:** Deactivated developers blocked from login, 401 auto-redirect to login page

### Key Design Decisions
- GitHub OAuth over personal tokens — better UX, no token distribution needed
- JWT-based stateless sessions — no server-side session storage
- Per-endpoint auth injection (not router-level) to support mixed admin/developer access in same router
- `DEVPULSE_ADMIN_TOKEN` removed entirely — OAuth-only auth
- Developer nav shows only "My Stats" linking to their own detail page
- Repo stats open to all authenticated users (not sensitive per-developer data)
- AI, Sync endpoints admin-only (management features)
