# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

DevPulse — an engineering intelligence dashboard that tracks developer activity across GitHub repositories for an organization. Provides PR/review/cycle-time metrics, team benchmarks, trend analysis, workload balance, collaboration insights, developer goals, and optional on-demand AI analysis via Claude API.

**Core invariants:**
- AI is off by default; all stats are computed deterministically from raw data
- GitHub is the single source of truth; DevPulse is read-only (never writes back to GitHub)
- All GitHub data is cached locally in PostgreSQL to handle rate limits
- All backend I/O is async (SQLAlchemy async sessions, httpx.AsyncClient)

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async with asyncpg), Alembic migrations
- **Database:** PostgreSQL 15+ (async via asyncpg)
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui (base-nova style), TanStack Query v5, Recharts 3, pnpm
- **GitHub integration:** REST API via httpx, GitHub App auth (JWT + installation tokens)
- **AI:** Anthropic Claude API (claude-sonnet-4-0), on-demand only
- **Scheduling:** APScheduler AsyncIOScheduler (in-process, configured in FastAPI lifespan)
- **Testing:** pytest + pytest-asyncio (backend), aiosqlite for in-memory test DB

## Architecture

```
React Frontend (Vite :5173)  ──/api proxy──>  FastAPI Backend (:8000)  ──>  PostgreSQL (:5432)
                                                     ↕
                                              GitHub REST API (read-only)
                                                     ↕
                                              Claude API (on-demand AI analysis)
```

**Data flow:** GitHub App auth (JWT → installation token) → Scheduled sync fetches repos/PRs/reviews/issues → Webhooks for real-time updates → Stats service computes metrics on-demand → AI analysis optional.

### Backend Layout

```
backend/app/
├── api/              # FastAPI routers (thin delegation to services)
│   ├── auth.py, oauth.py        # JWT validation, GitHub OAuth
│   ├── developers.py, stats.py  # Team registry, all stats/benchmarks/trends/workload
│   ├── goals.py, sync.py        # Goals CRUD, sync trigger/status
│   ├── webhooks.py              # GitHub webhook receiver (HMAC-verified)
│   └── ai_analysis.py           # AI analysis + 1:1 prep + team health
├── models/
│   ├── database.py   # Async engine, session factory, Base, get_db()
│   └── models.py     # All SQLAlchemy ORM models
├── schemas/schemas.py # All Pydantic request/response models and enums
├── services/
│   ├── github_sync.py    # GitHub App auth, rate limiting, upsert helpers, sync orchestration
│   ├── stats.py          # All metrics: developer, team, repo, benchmarks, trends, workload
│   ├── collaboration.py  # Collaboration matrix + insights (silos, bus factors, isolation)
│   ├── goals.py          # Goal CRUD, metric computation, auto-achievement
│   ├── risk.py           # PR risk scoring: per-PR assessment, team risk summary
│   ├── ai_analysis.py    # Claude API integration, 1:1 prep briefs, team health checks
│   ├── work_category.py  # Work categorization: label/title/AI classification
│   └── ai_settings.py    # AI feature toggles, budget, pricing, cooldown, usage tracking
├── config.py         # pydantic-settings: all env vars (see also .env.example)
└── main.py           # FastAPI app factory, CORS, router registration, APScheduler
```

### Frontend Layout

```
frontend/src/
├── pages/            # Route components (Dashboard, TeamRegistry, DeveloperDetail, Repos, etc.)
│   ├── insights/     # Insights sub-pages (Workload, Collaboration, Benchmarks, IssueQuality, etc.)
│   ├── sync/         # Sync wizard, progress, history (SyncPage, SyncWizard, steps/, SyncProgressView, etc.)
│   └── settings/     # Settings pages (AISettings)
├── components/
│   ├── Layout.tsx    # Sticky header, nav (with Insights dropdown), global date range picker
│   ├── StatCard.tsx, StatCardSkeleton.tsx, TableSkeleton.tsx, ErrorCard.tsx, ErrorBoundary.tsx
│   ├── StalePRsSection.tsx, GoalCreateDialog.tsx, DateRangePicker.tsx
│   ├── ai/           # AI result renderers (AnalysisResultRenderer, OneOnOnePrepView, etc.)
│   ├── charts/       # TrendChart, PercentileBar, ReviewQualityDonut, GoalSparkline
│   └── ui/           # shadcn/ui primitives
├── hooks/            # TanStack Query hooks (useAuth, useDevelopers, useStats, useSync, useAI, useAISettings, useGoals, useDateRange)
├── utils/            # api.ts (apiFetch wrapper), types.ts (TS interfaces)
└── lib/utils.ts      # cn() utility (clsx + tailwind-merge)
```

**Import alias:** `@/` maps to `src/` (configured in vite.config.ts and tsconfig).

## Database Schema (16 tables)

| Table | Purpose |
|-------|---------|
| `developers` | Team registry with GitHub username, role, team, skills, app_role |
| `repositories` | GitHub repos with tracking toggle, default branch, tree truncation flag |
| `pull_requests` | PRs with pre-computed cycle times, approval tracking, issue linkage, head_sha |
| `pr_reviews` | Reviews with quality tier classification |
| `pr_review_comments` | Inline code review comments with type classification |
| `pr_files` | File-level changes per PR (filename, additions, deletions, status) |
| `pr_check_runs` | CI/CD check runs per PR (name, conclusion, duration, attempt) |
| `repo_tree_files` | Full repo file tree snapshot for stale directory detection |
| `issues` | Issues with close-time computation and quality scoring |
| `issue_comments` | Issue comment bodies |
| `sync_events` | Sync run audit log with per-repo progress, resumability, structured errors, log_summary |
| `ai_analyses` | AI analysis results (JSONB) with split token tracking + cost |
| `ai_settings` | Singleton (id=1) AI feature toggles, budget, pricing config |
| `ai_usage_log` | Token usage tracking for work categorization AI calls |
| `deployments` | DORA deployment records from GitHub Actions workflow runs |
| `developer_goals` | Goal tracking with metric targets + `created_by` (self/admin) |

**Key design decisions:**
- Author/reviewer FKs are **nullable** — external contributors get `NULL`
- PR cycle-time fields pre-computed at sync time; issue has `time_to_close_s`
- JSONB columns: `skills`, `labels`, `errors`, `result`, `closes_issue_numbers`, `repos_completed`, `repos_failed`, `log_summary`, `repo_ids`
- `developer_goals.created_by` — `"self"` or `"admin"`; developers can only modify their own self-created goals
- No commit-level data — stats are PR-level only to stay within GitHub rate limits

## Running

### Docker (recommended)
```bash
cp .env.example .env   # edit with your values
docker compose up
```
Backend: http://localhost:8000 | Frontend: http://localhost:3001 | DB: localhost:5432

### Local development
```bash
# Backend
cd backend && pip install -r requirements.txt && alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend && pnpm install && pnpm dev
```

### Migrations & tests
```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
pip install -r requirements-test.txt
python -m pytest                    # all tests (SQLite in-memory, no PostgreSQL needed)
python -m pytest tests/unit/        # unit tests only
```

## Key Patterns and Conventions

### Backend
- **Auth:** GitHub OAuth → JWT (7-day expiry). Roles: `admin` (full access), `developer` (own data only). `get_current_user()` → `AuthUser`, `require_admin()` → 403. Per-endpoint injection for mixed-access routers.
- **Thin API routes:** Validate input, delegate to service functions — no business logic in routes
- **Service functions:** All async, accept `AsyncSession` as first param
- **Upsert pattern:** SELECT by unique key → create if not found → always overwrite mutable fields
- **Date range defaulting:** `_default_range()` — defaults to last 30 days if params are None
- **Review quality tiers:** `classify_review_quality()` pure function at sync time, recomputed after review comments via `recompute_review_quality_tiers()`. Tiers: thorough, standard, rubber_stamp, minimal.
- **Comment type classification:** `classify_comment_type()` keyword-based: nit, blocker, architectural, question, praise, suggestion, general (default)
- **Percentile band inversion:** For lower-is-better metrics, `_percentile_band()` inverts labels so `above_p75` always means "best"
- **Trend regression:** Simple OLS `_linear_regression()` with polarity-aware direction; <5% change = "stable"
- **Draft PR filtering:** `PullRequest.is_draft.isnot(True)` excludes drafts from open counts, workload, stale alerts
- **Workload score:** `total_load = open_authored + open_reviewing + open_issues`. Thresholds: low(0), balanced(1-5), high(6-12), overloaded(>12)
- **PR risk scoring:** Pure `compute_pr_risk()` in `services/risk.py`, 10 weighted factors, score 0-1. Levels: low/medium/high/critical
- **AI guards:** All AI call sites check feature toggles → budget → cooldown before calling Claude. `ai_settings` singleton controls everything.
- **Work categorization:** Label map → title regex → "unknown". Optional AI batch classification. Categories: feature, bugfix, tech_debt, ops, unknown.
- **Sync architecture:** `SyncContext` dataclass threads db/client/sync_event/logger through the sync chain. Per-repo `db.commit()` after each repo + batch commits every 50 PRs within large repos. JSONB columns mutated via `_append_jsonb()` helper (reassigns to trigger SQLAlchemy change detection). Rollback+merge pattern on per-repo failure preserves log_summary. Structured errors via `make_sync_error()`. Retry with exponential backoff on 502/503/504.
- **Sync API:** `POST /sync/start` (SyncTriggerRequest), `POST /sync/resume/{id}`, `GET /sync/status` (SyncStatusResponse), concurrency guard (409). Scheduler uses `scheduled_sync()` wrapper with concurrency check.
- **Sync statuses:** `started` → `completed` | `completed_with_errors` | `failed`. `is_resumable=True` when failed/partial.

### Frontend
- **Global date range:** `DateRangeContext` set in Layout header, consumed by all pages
- **Server state:** TanStack Query with 30s stale time, 1 retry
- **Auth:** JWT in `localStorage` key `devpulse_token`, injected by `apiFetch()`. Auto-redirect to `/login` on 401.
- **API proxy:** Vite dev server proxies `/api/*` → `http://localhost:8000`
- **Component library:** shadcn/ui with base-nova style, neutral base color, CSS variables, Lucide icons
- **Charts:** Recharts 3 in `components/charts/`. Use `ResponsiveContainer`, CSS variables for colors, `useId()` for unique SVG gradient IDs
- **Trend deltas:** Frontend compares current vs previous period. For lower-is-better metrics, green = decrease
- **Toast notifications:** `sonner` (bottom-right, 4s auto-dismiss). All mutations wrapped with success/error toasts.
- **Error/loading:** `ErrorCard` + `ErrorBoundary` for errors. `StatCardSkeleton` + `TableSkeleton` for loading.
- **AI result rendering:** `AnalysisResultRenderer` switches on `analysis_type` → structured view. Colors: green (positive), amber (attention), red (concern).
- **Nav groups:** Layout supports dropdown groups with `children` array. "Insights" group holds 8 sub-pages.
- **Batch developer stats:** `useAllDeveloperStats()` uses `useQueries` for parallel fetch, cache-shared with `useDeveloperStats`.
- **AI settings page:** `/settings/ai` admin-only page with master switch, per-feature toggle cards, budget config, pricing config, usage stacked area chart, cooldown setting. Auto-saves on change (debounced 500ms). `useAISettings` hook fetches settings, `useUpdateAISettings` patches.
- **AI dedup banners:** When AI mutation returns `reused: true`, history items show a "cached" badge and a blue info banner with "Regenerate" button (`force=true`). Cost estimates shown in AI trigger dialogs via `useAICostEstimate`.
- **AI budget warning:** AIAnalysis page shows amber banner when `budget_pct_used >= budget_warning_threshold` with link to AI Settings. Investment page checks `feature_work_categorization` before toggling AI classify.

## Reference Docs

- `docs/API.md` — Complete API reference with all endpoints and request/response schemas
- `DEVPULSE_SPEC.md` — Full technical specification
- `DEVPULSE_MANAGEMENT_FEATURES.md` — Management features spec (M1-M8)
- `.env.example` + `backend/app/config.py` — All environment variables
