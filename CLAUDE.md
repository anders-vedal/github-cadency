# CLAUDE.md

## Project

DevPulse — engineering intelligence dashboard tracking developer activity across GitHub repos. PR/review/cycle-time metrics, team benchmarks, trend analysis, workload balance, collaboration insights, goals, and optional AI analysis.

**Core invariants:**
- AI is off by default; all stats are computed deterministically from raw data
- GitHub is the source of truth for code activity; DevPulse never writes back to GitHub
- Linear is the primary issue/sprint tracker (Jira support planned). `is_primary_issue_source` flag on `integration_config` controls which issue table stats query.
- All synced data cached locally in PostgreSQL
- All backend I/O is async (SQLAlchemy async sessions, httpx.AsyncClient)

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async/asyncpg), Alembic, APScheduler
- **Database:** PostgreSQL 15+
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui (base-nova), TanStack Query v5, Recharts 3, pnpm
- **Integrations:** GitHub REST API (read-only, App auth), Linear GraphQL API (primary issue tracker), Claude API (on-demand), Slack (bot token)
- **Testing:** pytest + pytest-asyncio, aiosqlite for in-memory test DB
- **Error monitoring:** Nordlabs convention — ErrorClassifier + ErrorReporter → Sentinel

## Architecture

```
React Frontend (Vite :5173)  ──/api proxy──>  FastAPI Backend (:8000)  ──>  PostgreSQL (:5432)
                                                     ↕
                                         GitHub / Linear / Claude APIs
```

### Backend Layout

```
backend/app/
├── api/              # FastAPI routers (thin — delegate to services)
├── models/
│   ├── database.py   # Async engine, session factory, Base, get_db()
│   └── models.py     # All ORM models (39 tables)
├── schemas/schemas.py # All Pydantic request/response models
├── services/         # Business logic (all async, accept AsyncSession as first param)
├── libs/errors.py    # Nordlabs error convention (ErrorCategory, Classifier, Sanitizer, Reporter)
├── logging/          # structlog setup + request context middleware
├── config.py         # pydantic-settings (all env vars)
├── rate_limit.py     # slowapi config
└── main.py           # App factory, CORS, middleware, router registration, APScheduler
```

### Frontend Layout

```
frontend/src/
├── pages/            # Route components (lazy-loaded)
│   ├── insights/     # Workload, Collaboration, Benchmarks, DORA, Sprints, Planning, Projects
│   ├── sync/         # Sync wizard, progress, history
│   ├── ai/           # AI analysis wizard
│   └── settings/     # AI, Slack, Notification settings
├── components/       # UI components, charts/, ui/ (shadcn primitives)
├── hooks/            # TanStack Query hooks
├── utils/            # api.ts (apiFetch), types.ts, format.ts, logger.ts
└── lib/utils.ts      # cn() (clsx + tailwind-merge)
```

**Import alias:** `@/` maps to `src/`.

## Running

```bash
# Docker (recommended)
cp .env.example .env && docker compose up
# Backend: :8000 | Frontend: :3001 | DB: :5433

# Local dev
cd backend && pip install -r requirements.txt && alembic upgrade head && uvicorn app.main:app --reload
cd frontend && pnpm install && pnpm dev

# Tests (SQLite in-memory, no PostgreSQL needed)
cd backend && pip install -r requirements-test.txt && python -m pytest

# Migrations
cd backend && alembic revision --autogenerate -m "description" && alembic upgrade head

# Observability stack (opt-in)
docker compose --profile logging up
```

## E2E Tests

Playwright-based end-to-end tests live in `e2e/`. Page objects in `e2e/pages/`, test specs in `e2e/tests/` (smoke + insights suites). Config in `e2e/playwright.config.ts` — targets `localhost:5173`, uses `global-setup.ts` for DB seeding and auth state.

```bash
cd e2e && pnpm install && pnpm exec playwright test          # all tests
cd e2e && pnpm exec playwright test --project=chromium-smoke  # smoke suite only
```

Requires backend + frontend running (Playwright auto-starts them locally via `webServer` config, skipped in CI). Uses `docker-compose.e2e.yml` for isolated DB seeding.

## Key Patterns

### Backend

- **Auth:** GitHub OAuth → JWT (4h). Roles: `admin` (full), `developer` (own data). `get_current_user()` → `AuthUser`, `require_admin()` → 403. `token_version` on developers invalidates JWTs on role change/deactivation.
- **Service pattern:** All async, `AsyncSession` as first param. Thin API routes delegate to services — no business logic in routes.
- **Upsert pattern:** SELECT by unique key → create if missing → overwrite mutable fields.
- **Date ranges:** `_default_range()` defaults to last 30 days if params are None.
- **Contribution categories:** `code_contributor`, `issue_contributor`, `non_contributor`, `system`. Controls stats inclusion. Roles are admin-configurable via `role_definitions` table.
- **Work categorization cascade:** label rules → issue type rules → title regex/prefix → cross-reference → AI (optional) → "unknown". Manual overrides (`source="manual"`) never overwritten. ReDoS protection on regex rules.
- **Sync (GitHub):** `SyncContext` threads db/client/sync_event/logger. Per-repo commits + batch commits every 50 PRs. PostgreSQL advisory lock prevents concurrent syncs. Cancellation checked at repo boundaries and every 50-PR batch. `resolve_author()` auto-creates developers from GitHub user data.
- **Sync (Linear):** `run_linear_sync()` orchestrates projects → cycles → issues → PR linking → developer mapping. Concurrency guard via active `SyncEvent` check. `_check_linear_cancel()` at each step boundary and every 50 issues. `_add_log()` writes structured entries to `sync_event.log_summary`. Rate limit handling in `LinearClient.query()` (proactive slowdown + 429 retry). Live-configurable schedule via `linear_sync_enabled`/`linear_sync_interval_minutes` on `SyncScheduleConfig`. Post-sync triggers `evaluate_all_alerts()` for planning notifications.
- **AI guards:** All AI call sites check feature toggles → budget → cooldown before calling Claude. `AIFeatureDisabledError` → 403, `AIBudgetExceededError` → 429 (handled globally).
- **AI context enrichment:** 1:1 prep (`build_one_on_one_context`) and team health (`build_team_health_context`) include Linear sprint data when an active integration + developer mapping exists. `gather_sprint_context_for_developer()` adds active sprint, recent sprints, triage stats, estimation patterns. `gather_planning_health_context()` adds velocity trend, completion rate, scope creep, triage health, estimation accuracy, work alignment, at-risk projects. Both return `None` gracefully when Linear is not configured.
- **Encryption:** Shared Fernet in `services/encryption.py` for Slack tokens and Linear API keys. Requires `ENCRYPTION_KEY` env var.
- **Issue tracker integration:** Linear is the primary issue tracker. Generic `integration_config` table (type column) designed for future Jira support. Stats functions branch on `get_primary_issue_source()` to query `issues` (GitHub) or `external_issues` (Linear) table — covers developer stats, team stats, repo stats, issue linkage, issue quality, issue creators, work categorization, work allocation, benchmarks, and trends. `developer_identity_map` links developers to external system accounts. Workload includes `sprint_commitment` context (active sprint progress, on-track status) when Linear is primary.
- **Collaboration scores:** Materialized post-sync from 5 signals (review 0.35, co-author 0.15, issue comments 0.20, mentions 0.15, co-assignment 0.15). Canonical pair ordering (`a_id < b_id`). Co-assignment signal includes Linear sprint co-membership when active (additive — developers in same sprint count as co-assigned).
- **Notifications:** 22 alert types (16 GitHub + 6 planning), dedup by `alert_key`, auto-resolution, per-user read/dismiss tracking with optional expiry. Planning alerts (`velocity_declining`, `scope_creep_high`, `sprint_at_risk`, `triage_queue_growing`, `estimation_accuracy_low`, `linear_sync_failure`) evaluated via `_evaluate_planning_alerts()` — no-op when Linear not configured. Issue linkage evaluator branches on primary issue source (`pr_external_issue_links` for Linear, `closes_issue_numbers` for GitHub).
- **Logging:** structlog with `event_type` taxonomy. JSON in prod, console in dev. `LoggingContextMiddleware` injects `request_id`.
- **Error handling:** `libs/errors.py` — classifies all exceptions into 8 categories, only reports `app_bug` to Sentinel after frequency threshold.
- **Rate limiting:** slowapi, default 120/min. Disabled via `RATE_LIMIT_ENABLED=false` in tests.

### Frontend

- **State:** TanStack Query (30s stale, 1 retry). JWT in `localStorage` key `devpulse_token`.
- **Styling:** shadcn/ui base-nova, CSS variables, Lucide icons. `sonner` for toasts.
- **Charts:** Recharts 3, `ResponsiveContainer`, CSS vars for colors, `useId()` for SVG gradient IDs.
- **Error handling:** `ErrorCard` + per-section `ErrorBoundary`. `StatCardSkeleton`/`TableSkeleton` for loading.
- **Code splitting:** All pages lazy-loaded via `React.lazy()`.
- **Nav:** Top nav (Dashboard, Executive, Insights, Goals, Admin dropdown). Insights + Admin use `SidebarLayout`. `isNavActive()` uses prefix matching. Sprint/Planning/Projects sidebar links conditionally rendered based on `useIntegrations()` — shows "Sprint Planning ›" setup link when Linear not configured.
- **Date range:** Global `DateRangeContext` in Layout header, consumed by all pages.
- **Trend deltas:** Current vs previous period. For lower-is-better metrics, green = decrease.
- **AI rendering:** `components/ai/` — structured views for AI analysis output. `AnalysisResultRenderer` dispatches by analysis type to `GenericAnalysisView` (general), `OneOnOnePrepView` (1:1 prep briefs), or `TeamHealthView` (team health). Each renders Claude API JSON as themed card layouts with sections, recommendations, and metrics.

## Architecture Advisory

Consult `docs/architecture/` before adding new tables, routers, or services:

| File pattern | Relevant doc |
|-------------|--------------|
| `models/models.py` | `docs/architecture/DATA-MODEL.md` |
| `models/database.py` | `docs/architecture/SERVICE-LAYER.md` |
| `schemas/schemas.py` | `docs/architecture/API-DESIGN.md` |
| `main.py` | `docs/architecture/OVERVIEW.md` |
| `api/*.py` (new routers) | `docs/architecture/API-DESIGN.md` |
| `services/*.py` (new) | `docs/architecture/SERVICE-LAYER.md` |
| `migrations/versions/*.py` | `docs/architecture/DATA-MODEL.md` |
| `pages/*.tsx` (new pages) | `docs/architecture/FRONTEND.md` |

After structural changes, run `/architect <area>` to update docs.

## Reference Docs

- `docs/API.md` — Complete API reference
- `docs/architecture/` — Architecture documentation
- `DEVPULSE_SPEC.md` — Full technical specification
- `.env.example` + `backend/app/config.py` — All environment variables
