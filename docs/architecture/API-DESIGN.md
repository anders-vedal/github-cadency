---
purpose: "Auth model, route patterns, schema conventions, error handling"
last-updated: "2026-03-29"
related:
  - docs/architecture/OVERVIEW.md
  - docs/architecture/SERVICE-LAYER.md
  - docs/architecture/DATA-FLOWS.md
---

# API Design

For the complete endpoint catalog, see [docs/API.md](../API.md).

## Authentication Model

### GitHub OAuth Flow

1. `GET /api/auth/login` returns GitHub OAuth URL
2. User authorizes on GitHub, redirected to frontend `/auth/callback?code=...`
3. Frontend relays code to `GET /api/auth/callback?code=...`
4. Backend exchanges code for token, fetches GitHub user, upserts Developer, creates JWT
5. Returns `302` redirect to frontend with JWT in query string

### JWT

- Algorithm: HS256, signed with `jwt_secret` env var
- Expiry: 7 days
- Payload: `{developer_id, github_username, app_role, exp}`
- Storage: frontend `localStorage` key `devpulse_token`

### Auth Dependencies (`backend/app/api/auth.py`)

| Dependency | Returns | Usage |
|------------|---------|-------|
| `get_current_user` | `AuthUser` | Decodes JWT + checks `developers.is_active` via DB; 401 if invalid, expired, deactivated, or deleted |
| `require_admin` | `AuthUser` | Admin only; 403 if `app_role != "admin"` |

### Auth Patterns by Router

| Router | Auth strategy |
|--------|--------------|
| `oauth.py` | Per-endpoint (`/auth/me` uses `get_current_user`, others unauthenticated) |
| `developers.py` | Per-endpoint (mixed `require_admin` and `get_current_user`) |
| `stats.py` | Per-endpoint (mostly `require_admin`, some `get_current_user` with self-check) |
| `sync.py` | Router-level `dependencies=[Depends(require_admin)]` |
| `goals.py` | Per-endpoint (mixed admin and self-service) |
| `ai_analysis.py` | Router-level `dependencies=[Depends(require_admin)]` |
| `webhooks.py` | HMAC `X-Hub-Signature-256` (manual verification, no JWT) |
| `relationships.py` | Per-endpoint (GET relationships/works-with: `get_current_user` with self-check; POST/DELETE/org-tree/over-tagged/communication-scores: `require_admin`) |
| `slack.py` | Per-endpoint (config/test/notifications: `require_admin`; user-settings GET/PATCH: `get_current_user`; user-settings/{id}: `require_admin`) |

## Route Organization

### Router Registration (`main.py`)

All routers registered under `/api` prefix:

| Router module | Provides | Tag |
|--------------|----------|-----|
| `oauth` | `/api/auth/*` | auth |
| `developers` | `/api/developers/*` | developers |
| `stats` | `/api/stats/*` | stats |
| `sync` | `/api/sync/*` | sync |
| `webhooks` | `/api/webhooks/*` | webhooks |
| `goals` | `/api/goals/*` | goals |
| `ai_analysis` | `/api/ai/*` | ai |
| `relationships` | `/api/developers/{id}/relationships`, `/api/org-tree`, `/api/developers/{id}/works-with`, `/api/stats/over-tagged`, `/api/stats/communication-scores` | relationships |
| `slack` | `/api/slack/*` | slack |

Plus standalone `GET /api/health` (no auth) in `main.py`.

### Thin Router Pattern

Routers validate input and delegate to service functions -- no business logic in routes.

**Exceptions to this pattern:**
- `developers.py` -- all CRUD is inline (simple ORM operations, no domain logic)
- `sync.py` -- `/sync/status`, `/sync/cancel`, `/sync/force-stop`, history/repo queries are inline reads
- `ai_analysis.py` -- `POST /ai/estimate` has ~75 lines of inline logic (should be a service)
- `oauth.py` -- callback handler does OAuth token exchange inline (self-contained flow)

### Entity Existence Checks

Routers perform `db.get(Model, id)` before delegating to services for endpoints with entity path params. Services receive validated entities, not raw IDs. This is the standard 404 pattern.

## Schema Conventions

### Pydantic Models (`backend/app/schemas/schemas.py`)

- `ConfigDict(from_attributes=True)` on all response models for ORM compatibility
- Create/Update models use strict field types; Response models use relaxed types (e.g., enum -> str)
- Computed fields (not in DB): `DeveloperResponse.pr_count`, `AISettingsResponse.budget_pct_used`, `AIAnalysisResponse.reused`

### Enums

| Enum | Values | DB enforcement |
|------|--------|---------------|
| `DeveloperRole` | developer, senior_developer, lead, architect, devops, qa, intern | String column, no CHECK |
| `AppRole` | admin, developer | String column, no CHECK |
| `MetricKey` | prs_merged, prs_opened, time_to_merge_h, time_to_first_review_h, reviews_given, review_quality_score, issues_closed, avg_pr_additions | String column, no CHECK |
| `AnalysisType` | communication, conflict, sentiment | String column, no CHECK |

## Error Handling

### HTTP Status Codes

| Code | Usage |
|------|-------|
| 200 | Standard success |
| 201 | Resource created (POST /developers, POST /ai/analyze) |
| 202 | Async accepted (POST /sync/start, /sync/resume, /sync/contributors) |
| 204 | Deleted (DELETE /developers/{id}) |
| 401 | Invalid/missing JWT |
| 403 | Insufficient role or AI feature disabled |
| 404 | Entity not found |
| 409 | Conflict: sync already in progress, or duplicate developer username |
| 422 | Validation error (FastAPI auto) |
| 429 | AI budget exceeded |

### Error Format

`HTTPException(status_code=NNN, detail="Human-readable message")`. `detail` is usually a plain string.

**Exception:** `POST /developers` returns a structured `detail` dict (not a plain string) when 409 is triggered by an inactive username conflict: `{"code": "inactive_exists", "developer_id": int, "display_name": str}`. The frontend catches this via `ApiError` to offer a reactivation prompt.

**Minor inconsistency:** `sync.py` uses positional args (`HTTPException(409, "msg")`), other routers use kwargs.

## Background Tasks

`POST /sync/start`, `/sync/resume`, `/sync/contributors` use FastAPI `BackgroundTasks` to dispatch async work. The endpoint returns 202 immediately; the sync runs in the background with its own DB session.

## Architectural Concerns

| Severity | Area | Description |
|----------|------|-------------|
| ~~High~~ | ~~Bug~~ | ~~`sync.py` references `httpx.HTTPStatusError` but never imports `httpx`~~ — **Fixed**: `import httpx` added |
| Medium | Boundaries | `ai_settings.check_feature_enabled` and `ai_analysis.run_*` raise `HTTPException` from service layer |
| Medium | Thin router | `POST /ai/estimate` has significant inline business logic (~75 lines) |
| Medium | Organization | `/api/stats/over-tagged` and `/api/stats/communication-scores` are defined in `relationships.py`, not `stats.py` -- path prefix doesn't match router module |
| Low | Consistency | `GET /ai/history` uses manual column iteration for Pydantic construction; `GET /ai/history/{id}` and POST endpoints use `model_validate` |
| Low | Consistency | Positional vs keyword args for `HTTPException` across routers |
| Low | Auth | `GET /stats/repo/{repo_id}` uses `get_current_user` not `require_admin` -- any user can read any repo stats |
| Low | Efficiency | `PATCH /ai/settings` triggers `get_current_user` twice (router-level + endpoint-level) |
