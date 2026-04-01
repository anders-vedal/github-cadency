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
- **Rate limiting:** slowapi (IP-based, X-Forwarded-For–aware, configurable via `RATE_LIMIT_ENABLED`)
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
│   ├── developers.py, stats.py  # Team registry (CRUD + deactivation impact), all stats/benchmarks/trends/workload/repos summary
│   ├── goals.py, sync.py        # Goals CRUD, sync trigger/status/cancel/detail
│   ├── relationships.py         # Developer relationships, org tree, works-with, over-tagged, communication scores
│   ├── roles.py                 # Role definition CRUD (admin-configurable roles + contribution categories)
│   ├── work_categories.py       # Work category + rule CRUD, reclassify, suggestions scan, bulk rule create (admin-configurable)
│   ├── webhooks.py              # GitHub webhook receiver (HMAC-verified)
│   ├── ai_analysis.py           # AI analysis + 1:1 prep + team health
│   ├── slack.py                 # Slack integration config, user settings, test, notification history
│   ├── notifications.py         # Notification center: list, read, dismiss, config, evaluate (admin-only)
│   └── logs.py                  # Frontend log ingestion (POST /logs/ingest, no auth)
├── models/
│   ├── database.py   # Async engine, session factory, Base, get_db()
│   └── models.py     # All SQLAlchemy ORM models
├── schemas/schemas.py # All Pydantic request/response models and enums
├── services/
│   ├── exceptions.py     # Custom service exceptions (AIFeatureDisabledError, AIBudgetExceededError)
│   ├── github_sync.py    # GitHub App auth, rate limiting, upsert helpers, sync orchestration
│   ├── stats.py          # All metrics: developer, team, repo, repo summary (batch), benchmarks v2 (role-based peer groups), trends, workload
│   ├── collaboration.py  # Collaboration matrix + insights + pair detail + relationship classification
│   ├── enhanced_collaboration.py  # Multi-signal collaboration scoring, works-with, over-tagged, communication scores
│   ├── relationships.py  # Developer relationship CRUD + org tree builder
│   ├── roles.py          # Role definitions CRUD, category lookup, role validation
│   ├── goals.py          # Goal CRUD, metric computation, auto-achievement
│   ├── risk.py           # PR risk scoring: per-PR assessment, team risk summary
│   ├── ai_analysis.py    # Claude API integration, 1:1 prep briefs, team health checks
│   ├── work_categories.py # Configurable work categories: CRUD, classification rules, reclassify, GitHub data suggestions scan, bulk rule create
│   ├── work_category.py  # Work allocation: aggregation, drill-down, recategorization, AI batch
│   ├── ai_settings.py    # AI feature toggles, budget, pricing, cooldown, usage tracking
│   ├── slack.py          # Slack notifications: config CRUD, DM/channel sending, scheduled jobs
│   └── notifications.py  # Notification center: alert evaluation, materialization, read/dismiss, config CRUD
├── logging/
│   ├── __init__.py   # Public API: configure_logging, get_logger, LoggingContextMiddleware
│   ├── config.py     # structlog setup: processor pipeline, JSON/console output
│   └── middleware.py  # Request context middleware: request_id, method, path, duration
├── config.py         # pydantic-settings: all env vars (see also .env.example)
├── rate_limit.py     # slowapi Limiter instance, X-Forwarded-For–aware key function, default 120/min
└── main.py           # FastAPI app factory, CORS, rate limiting, router registration, APScheduler
```

### Frontend Layout

```
frontend/src/
├── pages/            # Route components (Dashboard, TeamRegistry, DeveloperDetail, Repos, etc.)
│   ├── insights/     # Insights sub-pages (Workload, Collaboration, Benchmarks, IssueQuality, IssueLinkage, OrgChart, etc.)
│   ├── sync/         # Sync wizard, progress, history, detail (SyncPage, SyncWizard, SyncDetailPage, SyncProgressView, etc.)
│   └── settings/     # Settings pages (AISettings, SlackSettings, NotificationSettings)
├── components/
│   ├── Layout.tsx    # Sticky header, top nav (Dashboard, Executive, Team, Insights, Goals, Admin dropdown), date range picker
│   ├── SidebarLayout.tsx # Sidebar navigation for section groups (Insights, Admin)
│   ├── StatCard.tsx, StatCardSkeleton.tsx, TableSkeleton.tsx, ErrorCard.tsx, ErrorBoundary.tsx
│   ├── AlertStrip.tsx    # Shared severity-based alert banner + workload style constants
│   ├── SortableHead.tsx  # Generic sortable table header with direction indicator
│   ├── StalePRsSection.tsx, GoalCreateDialog.tsx, DeactivateDialog.tsx, DateRangePicker.tsx
│   ├── PairDetailSheet.tsx   # Collaboration pair slide-over: summary stats, relationship badge, comment breakdown, PR list
│   ├── RelationshipsCard.tsx  # Relationship display/edit (reports_to, tech_lead, team_lead) on DeveloperDetail
│   ├── WorksWithSection.tsx   # Top collaborators with multi-signal score breakdown on DeveloperDetail
│   ├── SlackPreferencesSection.tsx  # Per-user Slack notification preferences on DeveloperDetail
│   ├── NotificationCenter/  # NotificationBell (header icon + badge), NotificationPanel (dropdown list), AlertSummaryBar (compact dashboard bar)
│   ├── ai/           # AI result renderers (AnalysisResultRenderer, OneOnOnePrepView, etc.)
│   ├── charts/       # TrendChart, PercentileBar, ReviewQualityDonut, GoalSparkline, DeploymentTimeline
│   └── ui/           # shadcn/ui primitives
├── hooks/            # TanStack Query hooks (useAuth, useDevelopers, useStats, useSync, useAI, useAISettings, useGoals, useDateRange, useRelationships, useRoles, useSlack, useNotifications)
├── utils/            # api.ts (apiFetch wrapper + ApiError class), types.ts (TS interfaces), categoryConfig.ts (CATEGORY_CONFIG/CATEGORY_ORDER), format.ts (timeAgo, formatDuration, formatDate shared utilities), logger.ts (structured frontend logger with batching + backend ingestion)
└── lib/utils.ts      # cn() utility (clsx + tailwind-merge)
```

**Import alias:** `@/` maps to `src/` (configured in vite.config.ts and tsconfig).

## Database Schema (29 tables)

| Table | Purpose |
|-------|---------|
| `developers` | Team registry with GitHub username, role, team, skills, app_role, token_version (for JWT revocation) |
| `repositories` | GitHub repos with tracking toggle, default branch, tree truncation flag |
| `pull_requests` | PRs with pre-computed cycle times, approval tracking, issue linkage, head_sha, author_github_username for backfill, work_category_source for classification provenance |
| `pr_reviews` | Reviews with quality tier classification, reviewer_github_username for backfill |
| `pr_review_comments` | Inline code review comments with type classification |
| `pr_files` | File-level changes per PR (filename, additions, deletions, status) |
| `pr_check_runs` | CI/CD check runs per PR (name, conclusion, duration, attempt) |
| `repo_tree_files` | Full repo file tree snapshot for stale directory detection |
| `issues` | Issues with close-time computation, quality scoring, issue_type (GitHub issue type name), creator_id + assignee_id FKs (both with github_username for backfill) |
| `issue_comments` | Issue comment bodies |
| `sync_events` | Sync run audit log with per-repo progress, granular step tracking, cancellation, resumability, structured errors, log_summary, triggered_by, sync_scope |
| `sync_schedule_config` | Singleton (id=1) auto-sync schedule: enabled toggle, incremental interval (minutes), full sync cron hour |
| `ai_analyses` | AI analysis results (JSONB) with split token tracking + cost |
| `ai_settings` | Singleton (id=1) AI feature toggles, budget, pricing config |
| `ai_usage_log` | Token usage tracking for work categorization AI calls |
| `deployments` | DORA deployment records from GitHub Actions workflow runs, with failure tracking (is_failure, failure_detected_via, recovery linkage) for CFR/MTTR |
| `developer_goals` | Goal tracking with metric targets + `created_by` (self/admin) |
| `developer_relationships` | Org hierarchy: reports_to, tech_lead_of, team_lead_of (generic relationship table) |
| `developer_collaboration_scores` | Materialized multi-signal collaboration scores per developer pair per period |
| `slack_config` | Singleton (id=1) global Slack integration config: bot token, notification toggles, thresholds, schedule |
| `slack_user_settings` | Per-developer Slack user ID + notification preference toggles |
| `notification_log` | Audit trail for sent Slack notifications (type, channel, status, payload) |
| `benchmark_group_config` | Admin-configurable peer group definitions: group_key, roles (JSONB), metrics (JSONB), display_order, min_team_size |
| `role_definitions` | Admin-configurable role definitions: role_key (PK), display_name, contribution_category, display_order, is_default. 13 default roles seeded. |
| `work_categories` | Admin-configurable work category definitions: category_key (PK), display_name, description, color, exclude_from_stats, display_order, is_default. 5 defaults seeded (feature, bugfix, tech_debt, ops, unknown) with descriptions. |
| `work_category_rules` | Admin-configurable classification rules: match_type (label/title_regex/prefix/issue_type), match_value, description, case_sensitive, category_key FK, priority. 31 default rules seeded. |
| `notifications` | Materialized in-app alerts with dedup (`alert_key` UNIQUE), severity, lifecycle (`resolved_at`), entity linking, metadata JSONB. 16 alert types. |
| `notification_reads` | Per-user read tracking: `(notification_id, user_id)` unique pair with `read_at` timestamp |
| `notification_dismissals` | Per-instance dismiss with optional expiry: `dismiss_type` (permanent/temporary), `expires_at` |
| `notification_type_dismissals` | Dismiss entire alert type per user: `(alert_type, user_id)` unique, with optional `expires_at` |
| `notification_config` | Singleton (id=1) admin-configurable alert thresholds, per-type enable toggles, contribution category exclusion, evaluation interval |

**Key design decisions:**
- Author/reviewer FKs are **nullable** — but `resolve_author()` auto-creates developers from embedded GitHub user data during sync. Raw usernames stored in `author_github_username`/`reviewer_github_username`/`assignee_github_username` columns for efficient backfill. `resolve_author()` also auto-reactivates inactive developers found in GitHub activity (flush + warning log).
- PR cycle-time fields pre-computed at sync time; issue has `time_to_close_s`
- JSONB columns: `skills`, `labels`, `errors`, `result`, `closes_issue_numbers`, `repos_completed`, `repos_failed`, `log_summary`, `repo_ids`
- `developer_goals.created_by` — `"self"` or `"admin"`; developers can only modify their own self-created goals
- `developer_relationships` uses generic `(source_id, target_id, relationship_type)` — supports multiple concurrent relationships (e.g., Alice reports to Bob and has Carol as tech lead)
- `developer_collaboration_scores` uses canonical pair ordering (`a_id < b_id`) to avoid duplicates. Materialized post-sync from 5 signals: PR reviews, co-repo authoring, issue co-comments, @mentions, co-assignment. Weights: reviews 0.35, issue comments 0.20, co-repos 0.15, mentions 0.15, co-assigned 0.15
- `mentions` JSONB on `pr_review_comments` and `issue_comments` — extracted at sync time via `extract_mentions()` regex, same pattern as `classify_comment_type()`
- `benchmark_group_config` stores admin-configurable peer groups (ICs, Leads, DevOps, QA). Each group maps roles to benchmark-relevant metrics. 4 default groups seeded by migration. `BENCHMARK_METRICS` registry in `stats.py` is the source of truth for all 15 benchmark-able metrics with label, direction, and unit.
- **Role definitions are admin-configurable** via `role_definitions` table. Each role has a `contribution_category`: `code_contributor` (devs, QA, leads), `issue_contributor` (PM, PO, EM, scrum master), `non_contributor` (designer), `system` (bots). Categories control stats inclusion: code contributors appear in PR/review benchmarks, issue contributors are excluded from code metrics but included in issue creator stats, system roles are excluded from everything. `ContributionCategory` enum is fixed; roles within categories are admin-managed via `GET/POST/PATCH/DELETE /roles`. Developers with `role=NULL` appear only in "All" view, not in any group.
- No commit-level data — stats are PR-level only to stay within GitHub rate limits

## Logging & Observability

### Structured Logging (structlog)

All backend logging uses structlog via `backend/app/logging/`:

```python
from app.logging import get_logger
logger = get_logger(__name__)
logger.info("Sync complete", repos=5, duration_s=42, event_type="system.sync")
```

- **JSON output** in Docker (prod), **console pretty-print** in local dev — controlled by `LOG_FORMAT` env var
- **Request correlation**: `LoggingContextMiddleware` auto-injects `request_id`, `method`, `path` into every log via contextvars
- **Event type taxonomy**: Every log call includes `event_type` for Loki label-based filtering:

| Namespace | Use |
|-----------|-----|
| `system.startup` / `system.shutdown` | App lifecycle |
| `system.http` | Request middleware (auto) |
| `system.sync` | Sync orchestration |
| `system.github_api` | GitHub API calls, rate limits |
| `system.scheduler` | APScheduler events |
| `system.webhook` | Webhook processing |
| `system.slack` | Slack notifications |
| `system.config` | Config validation |
| `ai.analysis` / `ai.categorization` / `ai.settings` | AI features |
| `frontend.error` / `frontend.warn` | Frontend errors (via ingestion) |

- **Frontend errors**: `frontend/src/utils/logger.ts` batches errors and ships to `POST /api/logs/ingest` (no auth). Initialized in `main.tsx` with global `onerror` + `unhandledrejection` handlers.
- **Sync log_summary**: The JSONB `SyncEvent.log_summary` is a separate user-facing system (powers the sync UI log viewer). It coexists with structlog.

### Observability Stack

Opt-in via Docker Compose profile:
```bash
docker compose --profile logging up
```

| Service | Port | Purpose |
|---------|------|---------|
| Grafana | 3002 | Log visualization, dashboards |
| Loki | 3100 | Log storage (90-day retention) |
| Promtail | — | Collects container stdout → Loki |
| Prometheus | 9090 | Container metrics |
| cAdvisor | 8080 | Docker container stats |

Config files in `infrastructure/`. Pre-built "App Health" dashboard auto-provisioned in Grafana.

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
- **Auth:** GitHub OAuth → JWT (4-hour expiry). Roles: `admin` (full access), `developer` (own data only). `get_current_user()` decodes JWT + queries `developers.is_active` and `token_version` (rejects deactivated/deleted users and revoked tokens with 401) → `AuthUser`, `require_admin()` → 403. Per-endpoint injection for mixed-access routers. `token_version` column on `developers` is incremented on role change or deactivation, invalidating existing JWTs.
- **Thin API routes:** Validate input, delegate to service functions — no business logic in routes
- **Service functions:** All async, accept `AsyncSession` as first param
- **Upsert pattern:** SELECT by unique key → create if not found → always overwrite mutable fields
- **Date range defaulting:** `_default_range()` — defaults to last 30 days if params are None
- **Review quality tiers:** `classify_review_quality()` pure function at sync time, recomputed after review comments via `recompute_review_quality_tiers()`. Tiers: thorough, standard, rubber_stamp, minimal.
- **Comment type classification:** `classify_comment_type()` keyword-based: nit, blocker, architectural, question, praise, suggestion, general (default)
- **Percentile band inversion:** For lower-is-better metrics, `_percentile_band()` inverts labels so `above_p75` always means "best"
- **Trend regression:** Simple OLS `_linear_regression()` with polarity-aware direction; <5% change = "stable"
- **DORA 4/4 metrics:** Deploy frequency, lead time, CFR, MTTR. `detect_deployment_failures()` in `github_sync.py` runs post-sync with 3 signals: failed workflow runs, revert PRs (48h window), hotfix PRs (configurable labels/branch prefixes via `HOTFIX_LABELS`/`HOTFIX_BRANCH_PREFIXES`). Recovery = next non-failure successful deploy. Overall DORA band = worst of all 4. DORA research thresholds for CFR: elite <5%, high <15%, medium <45%, low >=45%.
- **Draft PR filtering:** `PullRequest.is_draft.isnot(True)` excludes drafts from open counts, workload, stale alerts, deactivation impact
- **Activity summary:** `GET /developers/{id}/activity-summary` returns all-time stats: PRs authored/merged/open, reviews given, issues created/assigned, repos touched, first/last activity dates, work category breakdown (merged PRs classified via `classify_work_item()` fallback). Access: own profile or admin. `get_activity_summary()` in `stats.py` runs ~8 unfiltered aggregate queries. Repos-touched uses UNION of authored PR repos + reviewed PR repos. `last_activity` uses `COALESCE(merged_at, closed_at, created_at)` for immutable timestamps.
- **Developer deactivation:** `is_active` toggle via `PATCH /developers/{id}` (admin). `GET /developers/{id}/deactivation-impact` returns open PRs/issues/branches. `POST /developers` returns structured 409 `{code: "inactive_exists", developer_id, display_name}` when username exists but is inactive. `DELETE` remains as soft-delete for junk accounts. Sync auto-reactivates inactive devs with warning log. Frontend: active/inactive tabs on Team Registry, `DeactivateDialog` with impact preview, inactive badge on DeveloperDetail.
- **Workload score:** `total_load = open_authored + open_reviewing + open_issues`. Thresholds: low(0), balanced(1-5), high(6-12), overloaded(>12)
- **PR risk scoring:** Pure `compute_pr_risk()` in `services/risk.py`, 10 weighted factors, score 0-1. Levels: low/medium/high/critical
- **AI guards:** All AI call sites check feature toggles → budget → cooldown before calling Claude. `ai_settings` singleton controls everything. Services raise `AIFeatureDisabledError` (→ 403) and `AIBudgetExceededError` (→ 429) from `services/exceptions.py`; API routes catch and convert to HTTP responses. Claude client uses `max_retries=3` and `timeout=120s`.
- **Work categorization:** Admin-configurable via `work_categories` + `work_category_rules` tables. Classification cascade: label rules → issue type rules → title regex/prefix rules → cross-reference (PRs inherit from linked issues) → AI (optional) → "unknown". Rules evaluated by priority (lower = first). Categories are extensible (e.g., add "epic", "question", "security"). Both categories and rules have optional `description` fields for admin documentation. `exclude_from_stats` flag on categories removes items from metrics (Phase 2 for full stats integration, see `.claude/tasks/work-categories/phase2-stats-exclusion.md`). Classification persisted at sync time; "Reclassify All" button for rule changes. `work_category_source` tracks provenance: `label`, `title`, `prefix`, `issue_type`, `ai`, `manual`, `cross_ref`. Manual overrides (`source="manual"`) are authoritative and never overwritten. `classify_work_item_with_rules()` is a pure function accepting pre-loaded rules + optional `issue_type` parameter. `issues.issue_type` stores the GitHub issue type name (e.g., "Bug", "Epic", "Feature", "Task") captured at sync time from the REST API `type.name` field. Legacy items with NULL `work_category` fall back to rule-based classification at query time.
- **Work allocation items drill-down:** `GET /stats/work-allocation/items?category=&type=&page=&page_size=` returns paginated PRs/issues by computed category with repo name, author, labels, and category source. `PATCH /stats/work-allocation/items/{type}/{id}/category` recategorizes an item (sets `work_category_source="manual"`). Both endpoints use `get_current_user` (any authenticated user).
- **Sync architecture:** `SyncContext` dataclass threads db/client/sync_event/logger through the sync chain. Per-repo `db.commit()` after each repo + batch commits every 50 PRs within large repos. JSONB columns mutated via `_append_jsonb()` helper (reassigns to trigger SQLAlchemy change detection). Rollback+merge pattern on per-repo failure preserves log_summary. Structured errors via `make_sync_error()`. Retry with exponential backoff on 502/503/504. PostgreSQL advisory lock (`pg_advisory_lock`) prevents TOCTOU race on sync start (SQLite fallback for tests).
- **Sync granular progress:** `current_step` tracks the active phase within a repo (fetching_prs, processing_prs, fetching_issues, processing_issues, processing_issue_comments, syncing_file_tree, fetching_deployments). `current_repo_prs_total/done` and `current_repo_issues_total/done` provide item-level progress. Progress commits every 10 items; cleared between repos via `_clear_repo_progress()`.
- **Sync cancellation:** `cancel_requested` flag on `SyncEvent`, checked by `_check_cancel()` at repo boundaries and every 50-PR batch. Raises `SyncCancelled` → status becomes `"cancelled"` + `is_resumable=True`. `POST /sync/cancel` sets the flag; `POST /sync/force-stop` force-marks a stale sync as cancelled.
- **Sync API:** `POST /sync/start`, `POST /sync/resume/{id}`, `POST /sync/cancel`, `POST /sync/force-stop`, `POST /sync/contributors`, `GET /sync/status`, `GET /sync/events/{id}`, `GET /sync/events`, `POST /sync/discover-repos`, `GET /sync/repos`, `PATCH /sync/repos/{id}/track`, `GET /sync/schedule`, `PATCH /sync/schedule`. Concurrency guard (409). Scheduler uses `scheduled_sync()` wrapper.
- **Sync schedule config:** `sync_schedule_config` singleton (id=1) stores `auto_sync_enabled`, `incremental_interval_minutes`, `full_sync_cron_hour`. Loaded from DB on startup (falls back to env var defaults). `PATCH /sync/schedule` updates config and live-reschedules APScheduler jobs via `app.state.scheduler`. `scheduled_sync()` checks `auto_sync_enabled` before running.
- **Sync scope labels:** `sync_scope` on `SyncEvent` stores a human-readable description (e.g., "3 repos · 30 days", "All tracked repos · since last sync"). Computed by frontend for manual syncs, by backend for scheduled syncs. `triggered_by` tracks origin: "manual", "scheduled", "auto_resume". Both fields are nullable for backward compatibility with old events.
- **Contributor sync:** `sync_org_contributors()` fetches `GET /orgs/{org}/members` and upserts developers. Runs automatically at start of every `run_sync()`, and standalone via `POST /sync/contributors`. Standalone contributor sync creates a `SyncEvent(sync_type="contributors")` for progress tracking and concurrency — visible via `GET /sync/status` and in sync history. Uses `repos_synced` to store new developer count. `resolve_author()` auto-creates developers from PR/review/issue user data during upsert; also auto-reactivates inactive developers found in GitHub activity (flush + warning log). `sync_org_contributors()` similarly reactivates inactive org members. `backfill_author_links()` bulk-updates NULL author/reviewer/assignee FKs using stored github usernames with EXISTS guard. Separate commits for resilience.
- **Sync statuses:** `started` → `completed` | `completed_with_errors` | `failed` | `cancelled`. `is_resumable=True` when failed/partial/cancelled.
- **Sync logging:** `log_summary` JSONB capped at 500 entries with priority eviction (drops oldest info first). Verbose per-step entries: "Fetching PRs", "Found N PRs", "Processed X/Y PRs", step markers for issues/comments/tree/deployments.
- **@Mention extraction:** `extract_mentions()` regex runs at sync time in `upsert_review_comment()` and `upsert_issue_comment()`. Populates `mentions` JSONB column. Zero extra API calls.
- **Collaboration recomputation:** `recompute_collaboration_scores()` runs post-sync after backfill. Non-blocking — if it fails, sync still completes. Materializes scores into `developer_collaboration_scores`. Uses `since_override` or 90-day window for full syncs.
- **Developer relationships:** Generic `developer_relationships` table with `set_relationship()` / `remove_relationship()` service functions. Org tree built from `reports_to` relationships. Types: `reports_to`, `tech_lead_of`, `team_lead_of`.
- **Over-tagged detection:** Flags developers whose combined PR/issue tag rate exceeds team avg + 1.5 stddev or 50% absolute. Severity: mild/moderate/severe.
- **Communication score:** [0-100] per developer from 4 components (25pts each): review engagement, comment depth, reach, responsiveness. Computed on-demand.
- **Relationships API:** `GET/POST/DELETE /developers/{id}/relationships`, `GET /org-tree`, `GET /developers/{id}/works-with`, `GET /stats/over-tagged`, `GET /stats/communication-scores`.
- **Repos summary batch endpoint:** `GET /stats/repos/summary` returns per-repo metrics (PR count, merged count, avg merge time, issue count, review count, last PR date) for all tracked repos in one call using GROUP BY queries. Includes previous-period values for trend computation. 6 queries total (current + previous period). Uses `get_current_user` (not admin-only). Frontend derives health scores and trend arrows from this data.
- **Collaboration pair detail:** `GET /stats/collaboration/pair?reviewer_id=&author_id=` returns per-pair review stats, comment type breakdown, quality tier distribution, recent PRs with GitHub links, and relationship classification. 3 queries: reviews+PRs joined, comment type aggregation, reverse review count for asymmetry.
- **Pair relationship classification:** `classify_pair_relationship()` pure function in `collaboration.py` classifies reviewer→author pairs as: `mentor`, `peer`, `gatekeeper`, `rubber_stamp`, `one_way_dependency`, `casual`, or `none`. Uses review asymmetry, approval rate, quality tier score, and comment type distribution. Confidence scales with data volume. Input/output contract designed for future AI classifier swap via feature toggle.
- **Per-developer issue linkage:** `GET /stats/issue-linkage/developers` (admin) returns `IssueLinkageByDeveloper` with per-developer `prs_total`, `prs_linked`, `linkage_rate`, plus `attention_developers` (below threshold). `DeveloperStatsResponse` includes `prs_linked_to_issue` and `issue_linkage_rate`. Uses Python-side filtering (not `json_array_length`) for SQLite test compatibility. `issue_linkage_rate` available as benchmark metric in `BENCHMARK_METRICS` (Batch 10).
- **Benchmarks v2 (role-based peer groups):** `GET /stats/benchmarks?group=ics&team=platform` returns `BenchmarksV2Response` with per-developer metric values, percentile bands, and optional team comparison. Single API call replaces the old N+1 pattern. `_compute_per_developer_metrics()` accepts `requested_metrics` to only run needed batch queries (9 base + 6 extended: review_quality_score, changes_requested_rate, blocker_catch_rate, issues_closed, prs_merged_bugfix, issue_linkage_rate). Groups are admin-configurable via `GET/PATCH /stats/benchmark-groups`. `BENCHMARK_METRICS` dict is the canonical registry of all 15 benchmark metrics. Team comparison computes per-team medians when >=2 teams meet `min_team_size`. `GET /developers/unassigned-role-count` powers the nav badge for devs with no role set.
- **Benchmarks API:** `GET /stats/benchmark-groups` (admin, list groups), `PATCH /stats/benchmark-groups/{group_key}` (admin, update roles/metrics/min_team_size), `GET /stats/benchmarks?group=&team=` (admin, v2 response), `GET /developers/unassigned-role-count` (any user).
- **Roles API:** `GET /roles` (any user, list all role definitions), `POST /roles` (admin, create custom role), `PATCH /roles/{role_key}` (admin, update display_name/contribution_category/display_order), `DELETE /roles/{role_key}` (admin, only non-default roles with no assigned developers). Role validation on `POST/PATCH /developers` checks against `role_definitions` table.
- **Input validation:** Pydantic schemas enforce `Field(max_length=...)` on all user-facing string fields (e.g., `display_name=255`, `email=320`, `notes=5000`, `title=500`). `DeveloperCreate`/`DeveloperUpdate` share identical limits; `skills` items validated at 100 chars each via `field_validator`. Admin-supplied `title_regex` rules are checked for nested quantifiers (ReDoS protection) via `_validate_regex_safe()` in `work_categories.py` — patterns like `(a+)+$` are rejected at creation time. `GET /notifications` validates `severity` against `{"critical", "warning", "info"}` and `alert_type` against `ALERT_TYPE_META` registry keys. `POST /notifications/dismiss-type` also validates `alert_type`.
- **Work Categories API:** `GET /work-categories` (any user), `POST /work-categories` (admin), `PATCH /work-categories/{key}` (admin), `DELETE /work-categories/{key}` (admin, non-default only, no assigned items). `GET /work-categories/rules` (any user), `POST /work-categories/rules` (admin, validates regex + ReDoS check), `PATCH /work-categories/rules/{id}` (admin), `DELETE /work-categories/rules/{id}` (admin). `POST /work-categories/rules/bulk` (admin, creates multiple rules in one transaction). `POST /work-categories/reclassify` (admin, batch reclassifies all non-manual items using current rules). `POST /work-categories/suggestions` (admin, scans synced PR/issue data for uncovered labels and issue types, returns suggestions with usage counts and keyword-based category hints).
- **Slack integration:** Manual bot token setup (admin pastes xoxb- token). Bot token encrypted at rest using Fernet symmetric encryption (`ENCRYPTION_KEY` env var required). `encrypt_token()`/`decrypt_token()` in `services/slack.py`; `get_decrypted_bot_token()` handles decrypt failures gracefully. `slack_config` singleton for global settings, `slack_user_settings` for per-developer DM preferences (Slack user ID + notification toggles). 6 notification types: stale_pr, high_risk_pr, workload, sync_complete, sync_failure, weekly_digest. DMs sent to individual developers via `slack_sdk` `AsyncWebClient`. Scheduled jobs run hourly and check configured hour at runtime. Post-sync hook sends sync notifications. `notification_log` tracks all sent messages.
- **Slack API:** `GET/PATCH /slack/config` (admin), `POST /slack/test` (admin), `GET /slack/notifications` (admin), `GET/PATCH /slack/user-settings` (any user), `GET /slack/user-settings/{id}` (admin).
- **Log ingestion API:** `POST /logs/ingest` (public, no auth). Receives batched frontend error logs. Max 50 entries per request. Each entry emitted via structlog with `source="frontend"` and `event_type="frontend.error"`.
- **Rate limiting:** slowapi with IP-based throttling (X-Forwarded-For–aware). Default 120/minute on all routes. Tiered overrides: `/logs/ingest` 10/min, `/auth/login` + `/auth/callback` 10/min, `/webhooks/github` 60/min, `/sync/start` 5/min, `/notifications/evaluate` 5/min, `/work-categories/reclassify` 2/min. Limiter instance in `app/rate_limit.py`, registered on `app.state.limiter` in `main.py`. `SlowAPIMiddleware` added as outermost middleware (after CORS). Disabled via `RATE_LIMIT_ENABLED=false` (used in tests). Rate-limited endpoints require `request: Request` as first parameter. Uses in-memory storage (single-instance); Redis backend documented in `.env.example` for multi-instance.
- **Notification center:** Materialized alert system replacing unbounded AlertStrip stacking. `notifications` table stores alerts with `alert_key` dedup (UNIQUE), severity lifecycle (`resolved_at`), and entity linking. 16 alert types across 10 evaluators: stale PRs, workload (review bottleneck, underutilized, uneven assignment, merged without approval), revert spike, high-risk PRs, collaboration (bus factor, team silos, isolated developers), declining trends, issue linkage, AI budget, sync failures, config checks. `NotificationConfig` singleton (id=1) stores per-type enable toggles + configurable thresholds + `exclude_contribution_categories` JSONB (default: `["system", "non_contributor"]`). `ALERT_TYPE_META` registry in `notifications.py` drives the admin UI with labels, descriptions, and threshold metadata. Evaluation runs post-sync (non-blocking hook in `github_sync.py`) + scheduled every 15 minutes (configurable) + on-demand via `POST /notifications/evaluate`. Auto-resolution: `_auto_resolve_stale()` sets `resolved_at` on notifications whose conditions cleared. Per-user read tracking via `notification_reads` (separate from dismiss). Per-instance dismiss via `notification_dismissals` (permanent or temporary with `expires_at`). Per-type dismiss via `notification_type_dismissals`. Expired temporary dismissals ignored at query time.
- **Notification API:** `GET /notifications` (admin, with severity/alert_type/include_dismissed filters, pagination), `POST /notifications/{id}/read` (admin), `POST /notifications/read-all` (admin), `POST /notifications/{id}/dismiss` (admin, body: `{dismiss_type, duration_days?}`), `POST /notifications/dismiss-type` (admin, body: `{alert_type, dismiss_type, duration_days?}`), `DELETE /notifications/dismissals/{id}` (admin), `DELETE /notifications/type-dismissals/{id}` (admin), `GET/PATCH /notifications/config` (admin), `POST /notifications/evaluate` (admin).

### Frontend
- **Global date range:** `DateRangeContext` set in Layout header, consumed by all pages
- **Server state:** TanStack Query with 30s stale time, 1 retry
- **Auth:** JWT in `localStorage` key `devpulse_token`, injected by `apiFetch()`. Auto-redirect to `/login` on 401.
- **API proxy:** Vite dev server proxies `/api/*` → `http://localhost:8000`
- **Component library:** shadcn/ui with base-nova style, neutral base color, CSS variables, Lucide icons
- **Charts:** Recharts 3 in `components/charts/`. Use `ResponsiveContainer`, CSS variables for colors, `useId()` for unique SVG gradient IDs
- **Trend deltas:** Frontend compares current vs previous period. For lower-is-better metrics, green = decrease
- **Toast notifications:** `sonner` (bottom-right, 4s auto-dismiss). All mutations wrapped with success/error toasts.
- **Error/loading:** `ErrorCard` + per-section `ErrorBoundary` for errors (each top-level page and sidebar section wrapped individually, global boundary as fallback). `StatCardSkeleton` + `TableSkeleton` for loading.
- **Code splitting:** All page components lazy-loaded via `React.lazy()` with `Suspense` fallback (`PageSkeleton`). Layout, SidebarLayout, and shared hooks eagerly loaded.
- **AI result rendering:** `AnalysisResultRenderer` switches on `analysis_type` → structured view. Colors: green (positive), amber (attention), red (concern).
- **Nav structure:** Top nav has 4 links + Admin dropdown. Insights (`/insights/*`) and Admin (`/admin/*`) sections render with `SidebarLayout` (sticky left sidebar + content). Admin group: Team (`/admin/team`), Repos (`/admin/repos`), Sync (`/admin/sync`), AI Analysis (`/admin/ai`), AI Settings (`/admin/ai/settings`), Slack (`/admin/slack`), Work Categories (`/admin/work-categories`), Notifications (`/admin/notifications`). `isNavActive()` uses prefix matching for section links. Bare section URLs redirect to first sub-page. `/team` redirects to `/admin/team`; `/team/:id` (developer detail) remains top-level.
- **Contributor sync progress:** Team Registry page polls `useSyncStatus()` and shows a progress banner when `sync_type === "contributors"` is active. Completion banner (success/failure) fades after 10s via `useRef` transition detection. Developer list auto-refreshes on sync completion. Button disabled when any sync is active.
- **Developer deactivation UI:** Team Registry has Active/Inactive toggle tabs. Active tab: Edit + Deactivate buttons per row. Deactivate opens `DeactivateDialog` which fetches `GET /developers/{id}/deactivation-impact` to show open PRs, issues, and branches before confirming. Inactive tab: dimmed rows with Reactivate button. Creating a developer with an inactive username triggers structured 409 caught via `ApiError` with reactivation prompt. `DeveloperDetail` shows "Inactive" badge when `is_active=false`.
- **Activity summary on DeveloperDetail:** `ActivitySummaryCard` renders below the profile card (visible to own profile or admin). Shows lifetime PRs authored/merged/open, reviews given, issues created/assigned, repos touched, active since / last active dates, and a stacked color bar of work category breakdown (feature/bugfix/tech_debt/ops/unknown) with tooltips and legend. Uses `useActivitySummary` hook (60s staleTime).
- **Edit profile on DeveloperDetail:** Admin-only gear icon button on the profile card opens `EditProfileDialog` — edits display_name, email, role (grouped by contribution_category), team, office, location, timezone, skills. Uses `useUpdateDeveloper` mutation. Deactivate button in dialog footer closes edit dialog and opens `DeactivateDialog` for confirmation.
- **Sync schedule config:** `SyncScheduleCard` on Sync page — admin config with master toggle, interval input (min 5m), cron hour input. Auto-saves with 800ms debounce. `useSyncSchedule` / `useUpdateSyncSchedule` hooks. `SyncOverviewPanel` shows 5th card with "Next sync (~Xm)" countdown or "Disabled" state, computed from `last_successful_sync` + interval. Schedule config embedded in `SyncStatusResponse.schedule`.
- **Sync scope display:** History table, progress view, and detail page show `sync_scope` (e.g., "3 repos · 30 days") instead of raw "full"/"incremental". `triggered_by` shown as "Auto"/"Manual"/"Resumed" badge. Falls back to `sync_type` for old events without `sync_scope`. `computeSyncScope()` in `SyncWizard` derives the label from selected repos and time range.
- **Sync detail page:** `/admin/sync/:id` — `SyncDetailPage` shows live progress (reuses `SyncProgressView`), per-repo result cards, errors, filterable log. `useSyncEvent(id)` hook with adaptive polling (3s when active, stops when done). `SyncProgressView` renders a simpler view for `sync_type === "contributors"` (no repo progress bars, no cancel button).
- **Sync log filtering:** `SyncLogViewer` supports level filter (All/Info/Warn/Error), repo dropdown, auto-scroll toggle. Used in both `SyncProgressView` and `SyncDetailPage`.
- **Batch developer stats:** `useAllDeveloperStats()` uses `useQueries` for parallel fetch, cache-shared with `useDeveloperStats`.
- **Relationships card:** `RelationshipsCard` on DeveloperDetail shows reports_to/tech_lead/team_lead with add/remove dialogs (admin only). Uses `useRelationships`, `useCreateRelationship`, `useDeleteRelationship` hooks.
- **Works With section:** `WorksWithSection` on DeveloperDetail shows top 8 collaborators with multi-signal score breakdown. Uses `useWorksWith` hook.
- **Collaboration page:** `/insights/collaboration` — two main sections: `TeamHeatmap` (team×team aggregated grid from matrix data, click cell to filter pairs table, click again to clear) and `PairsTable` (all non-zero reviewer→author pairs, sortable by reviewer/author name or review count/approvals/changes requested, paginated at 25 rows, text search by name, "X Reviews" click opens `PairDetailSheet`, "Detail →" navigates to full pair page). Developers with `team=null` grouped as "Unassigned" in heatmap. Insights panel (Bus Factors, Team Silos, Isolated Developers) below. Team scope dropdown filters API-level data. All derived client-side from single `useCollaboration` call — no additional API requests vs old N×N heatmap. `PairDetailSheet` and `CollaborationPairPage` (`/insights/collaboration/:reviewerId/:authorId`) unchanged. TanStack Query cache hit makes pair page instant when navigating from sheet.
- **Org Chart page:** `/insights/org-chart` — tree visualization from `useOrgTree`. Expandable nodes, "not in hierarchy" section. Added to Insights sidebar.
- **Issue Linkage page:** `/insights/issue-linkage` — admin-only page showing per-developer PR-to-issue linkage rates. Summary stat cards (total PRs, linked PRs, team avg, attention count), amber "Attention Needed" callout card listing developers below threshold (<20%), sortable developer table with linkage rate bars. Team filter dropdown. `useIssueLinkageByDeveloper` hook. `DeveloperDetail` shows "Issue Linkage" StatCard in stats grid.
- **AI settings page:** `/admin/ai/settings` admin-only page with master switch, per-feature toggle cards, budget config, pricing config, usage stacked area chart, cooldown setting. Auto-saves on change (debounced 500ms). `useAISettings` hook fetches settings, `useUpdateAISettings` patches.
- **AI dedup banners:** When AI mutation returns `reused: true`, history items show a "cached" badge and a blue info banner with "Regenerate" button (`force=true`). Cost estimates shown in AI trigger dialogs via `useAICostEstimate`.
- **AI budget warning:** AIAnalysis page shows amber banner when `budget_pct_used >= budget_warning_threshold` with link to AI Settings. Investment page checks `feature_work_categorization` before toggling AI classify.
- **Slack settings page:** `/admin/slack` — admin-only page with connection status banner, bot token input (masked), default channel, master toggle, per-notification-type toggle cards, threshold config (stale PR days, risk score), schedule config (digest day/hour, stale check hour), notification history table. Auto-saves on change (debounced 500ms for text, immediate for toggles). Added to Admin sidebar and dropdown.
- **Slack preferences on DeveloperDetail:** `SlackPreferencesSection` renders on own profile only. Shows Slack user ID input and per-notification-type toggles. Uses `useSlackUserSettings` / `useUpdateSlackUserSettings` hooks.
- **Work Categories page:** `/admin/work-categories` — admin-only page with four sections: categories table (add/edit/delete, color swatch, exclude_from_stats toggle), classification rules table (priority, match type badge, match value, category, add/edit/delete), GitHub suggestions card (scan synced data for uncovered labels/issue types, review-and-approve flow with editable category dropdowns, approve individually or bulk "Approve All"), and reclassify card (batch reclassify all non-manual items). `useWorkCategories` / `useWorkCategoryRules` / `useReclassify` / `useScanSuggestions` / `useBulkCreateRules` hooks. `useCategoryConfig()` replaces static `CATEGORY_CONFIG` — returns `{ config, order }` from API with `FALLBACK_CATEGORY_CONFIG` while loading.
- **Benchmarks v2 page:** `/insights/benchmarks?group=ics&team=platform` — role-based peer group comparison. Group tabs (segmented control), team dropdown, percentile distribution table, sortable developer ranking table with per-metric percentile band badges and mini bars, team comparison table (when "All teams" and >=2 teams meet min size). URL-driven state via `useSearchParams` for shareable links. Single `useBenchmarksV2` API call (no N+1). `useBenchmarkGroups` fetches group config. Metric formatting driven by `metric_info` from backend (no hardcoded `metricConfigs`). Empty state links to Team Registry for role assignment.
- **Unassigned role nav badge:** Layout fetches `useUnassignedRoleCount()` and shows a red count badge next to "Team" in the Admin dropdown when active developers have `role=NULL`. `NavDropdown` accepts optional `badges` prop keyed by route path.
- **Repos page v2:** `/admin/repos` — portfolio-level repo management with summary strip (4x `StatCard`: tracked/untracked/never-synced counts + org-wide avg merge time with trend), search + filter bar (text search, language, status, health), sortable table (6 columns: Repository, Language, PRs, Avg Merge Time, Health, Tracked) and card grid view toggle. Health indicators (green/yellow/red/gray) computed frontend-side from `useReposSummary()` batch data: critical (>48h merge or zero PRs), attention (>24h merge or >14d stale), healthy, unknown (untracked). Trend arrows on PR count and merge time columns compare current vs previous period. Expandable row shows detailed stats via `useRepoStats()` plus deep-link buttons to DORA, CI, and Code Churn insight pages (`?repo_id=`). Health filter disabled during summary load to prevent flash of empty results. `useReposSummary` hook with 60s staleTime.
- **Investment v2 drill-down:** `/insights/investment` — clickable donut segments + legend items set `selectedCategory` state, showing inline 5-item preview via `useWorkAllocationItems`. "View all" links to `/insights/investment/:category` — `InvestmentCategory` page with paginated table, type filter (PR/Issue/All), category source badges, and per-row recategorization dropdown. Custom chart tooltips (`ChartTooltip`, `TrendTooltip`) replace default Recharts tooltips. Larger donuts (280px, 70/100 radii). Selected segment dims others (opacity 0.3) + ring highlight.
- **Insight page deep linking:** DORA (`/insights/dora`), CI (`/insights/ci`), and Code Churn (`/insights/code-churn`) pages accept `?repo_id=` URL parameter to pre-select a repo via `useSearchParams`. CodeChurn validates URL-sourced `repo_id` against tracked list on load.
- **Notification center bell:** `NotificationBell` in Layout header (admin only). Red badge with unread count. Click opens `NotificationPanel` dropdown (380px, max-height 400px, scrollable). Severity filter tabs (All/Critical/Warning/Info with counts). Notifications grouped by severity when "All" selected (critical expanded by default). Each item: severity dot, title, body preview, relative time, alert type badge, dismiss menu, link arrow. Clicking navigates to `link_path` and marks read. `DismissMenu`: dismiss instance (permanent/7d/30d) or mute entire alert type (permanent/7d). Footer links to Notification Settings page. Empty state: green checkmark "All clear".
- **Alert summary bar:** `AlertSummaryBar` replaces `AlertStrip` on Dashboard and Workload pages. Compact single-line: "2 critical, 3 warnings, 1 info" with severity-colored text. Shows green "All clear" when zero alerts. Links to notification center.
- **Notification settings page:** `/admin/notifications` — admin-only page with alert type cards grouped by category (Code Review, Workload, Risk, Collaboration, Trend, System). Each card: label, description, enable toggle, threshold inputs (auto-save with 800ms debounce). Contribution category exclusion multi-select. Evaluation interval config + "Evaluate now" button. `useNotificationConfig` / `useUpdateNotificationConfig` / `useEvaluateNotifications` hooks. Added to Admin sidebar and dropdown.

## Architecture Advisory

When modifying files that affect system architecture, consult `docs/architecture/` before making changes:

| File pattern | Concern | Relevant doc |
|-------------|---------|--------------|
| `backend/app/models/models.py` | Database schema | `docs/architecture/DATA-MODEL.md` |
| `backend/app/models/database.py` | Connection/session patterns | `docs/architecture/SERVICE-LAYER.md` |
| `backend/app/schemas/schemas.py` | API contracts | `docs/architecture/API-DESIGN.md` |
| `backend/app/main.py` | App init, middleware, scheduler | `docs/architecture/OVERVIEW.md` |
| `backend/app/api/*.py` (new routers) | API design patterns | `docs/architecture/API-DESIGN.md` |
| `backend/app/services/*.py` (new services) | Service layer patterns | `docs/architecture/SERVICE-LAYER.md` |
| `backend/migrations/versions/*.py` | Migration patterns | `docs/architecture/DATA-MODEL.md` |
| `frontend/src/pages/*.tsx` (new pages) | Routing/nav structure | `docs/architecture/FRONTEND.md` |

**Before adding new tables, routers, or services:** Read the relevant architecture doc to follow established patterns. After completing structural changes, run `/architect <area>` to update documentation.

## Reference Docs

- `docs/API.md` — Complete API reference with all endpoints and request/response schemas
- `docs/architecture/` — Interconnected architecture documentation (generated by `/architect`)
- `DEVPULSE_SPEC.md` — Full technical specification
- `DEVPULSE_MANAGEMENT_FEATURES.md` — Management features spec (M1-M8)
- `.env.example` + `backend/app/config.py` — All environment variables
