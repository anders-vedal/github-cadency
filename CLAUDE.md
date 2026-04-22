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
├── api/                          # FastAPI routers (thin — delegate to services)
│   ├── bottlenecks.py            # /api/bottlenecks/* (CFD, WIP, Gini, silos, blocked chains, ping-pong, bus factor)
│   ├── conversations.py          # /api/conversations/* (Linear issue dialogue analytics)
│   ├── dora_v2.py                # /api/dora/v2 (DORA v2 + AI cohort split)
│   ├── flow.py                   # /api/flow/* (status transitions, regressions, triage bounces)
│   ├── linear_health.py          # /api/linear/usage-health + /api/linear/labels
│   ├── metrics.py                # /api/metrics/catalog (MetricSpec registry for governance)
│   ├── classifier_rules.py       # /api/admin/classifier-rules (incident + AI-cohort rule CRUD)
│   └── ...                       # existing: oauth, developers, stats, sync, sprints, integrations, etc.
├── models/
│   ├── database.py               # Async engine, session factory, Base, get_db()
│   └── models.py                 # All ORM models (~45 tables)
├── schemas/schemas.py            # All Pydantic request/response models
├── services/                     # Business logic (all async, accept AsyncSession as first param)
│   ├── linear_sync.py            # Linear GraphQL client, sync orchestration, 4-pass PR linker
│   ├── linear_health.py          # Phase 03: 5-signal usage-health computation
│   ├── linkage_quality.py        # Phase 02: PR↔issue linkage summary + disagreement detection
│   ├── issue_conversations.py    # Phase 04: chattiest issues, comment↔bounce scatter, first-response
│   ├── flow_analytics.py         # Phase 06: status-time dist, regressions, triage bounces, churn
│   ├── bottleneck_intelligence.py# Phase 07: 10 signals + top-5 digest
│   ├── developer_linear.py       # Phase 05: creator / worker / shepherd profiles
│   ├── github_timeline.py        # Phase 09: GraphQL timelineItems fetch + persist + derive aggregates
│   ├── pr_cycle_stages.py        # Phase 09: per-PR stage decomposition (draft→review→approve→merge)
│   ├── codeowners.py             # Phase 09: CODEOWNERS parse + bypass detection
│   ├── ai_cohort.py              # Phase 10: PR cohort classification (human/ai_reviewed/ai_authored/hybrid)
│   ├── dora_v2.py                # Phase 10: DORA 2024 bands + rework rate + cohort split
│   ├── incident_classification.py# Phase 10: hotfix/incident rule engine (default rules)
│   ├── metric_spec.py            # Phase 11: MetricSpec registry + BANNED_METRICS + import-time validation
│   ├── classifier_rules.py       # Phase 10 C3: admin CRUD + load helpers (merges with defaults)
│   └── ...                       # existing: stats, github_sync, notifications, collaboration, etc.
├── libs/errors.py                # Nordlabs error convention (ErrorCategory, Classifier, Sanitizer, Reporter)
├── logging/                      # structlog setup + request context middleware
├── config.py                     # pydantic-settings (all env vars)
├── rate_limit.py                 # slowapi config
└── main.py                       # App factory, CORS, middleware, router registration, APScheduler
```

### Frontend Layout

```
frontend/src/
├── pages/                        # Route components (lazy-loaded)
│   ├── insights/                 # Workload, Collaboration, Benchmarks, DORA, Sprints, Planning,
│   │                             #   Projects, IssueConversations, FlowAnalytics, Bottlenecks
│   ├── admin/                    # LinkageQuality, MetricsGovernance, ClassifierRules
│   ├── sync/                     # Sync wizard, progress, history
│   ├── ai/                       # AI analysis wizard
│   └── settings/                 # AI, Slack, Notification settings
├── components/
│   ├── linear-health/            # Phase 03: LinearUsageHealthCard + CreatorOutcomeMiniTable
│   ├── developer/                # Phase 05: LinearCreatorSection / LinearWorkerSection / LinearShepherdSection
│   ├── charts/                   # CommentBounceScatter, LorenzCurve, CumulativeFlowDiagram, + existing
│   └── ui/                       # shadcn primitives
├── hooks/                        # TanStack Query hooks — one file per page/domain
├── utils/                        # api.ts (apiFetch), types.ts, format.ts, logger.ts
└── lib/utils.ts                  # cn() (clsx + tailwind-merge)
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
- **Sync (Linear):** `run_linear_sync()` orchestrates projects → project updates → cycles → issues (with per-issue depth: comments, history, attachments, relations) → PR linking → developer mapping. Concurrency guard via active `SyncEvent` check. `_check_linear_cancel()` at each step boundary and every 50 issues. `_add_log()` writes structured entries to `sync_event.log_summary` with counters for issues / comments / history_events / attachments / relations / project_updates / expansions_triggered. `LinearClient.query()` handles both HTTP 429 and HTTP 400 with `RATELIMITED` extension code; proactively sleeps when `X-RateLimit-Complexity-Remaining` drops below 10% of limit. Live-configurable schedule via `linear_sync_enabled`/`linear_sync_interval_minutes` on `SyncScheduleConfig`. Post-sync triggers `evaluate_all_alerts()` for planning + timeline notifications.
- **Linear sync depth (Phase 01):** Per-issue GraphQL expansion populates `external_issue_comments`, `external_issue_history` (structured from/to columns for state/assignee/estimate/priority/cycle/project/parent/labels), `external_issue_attachments` (with `normalized_source_type` classifier: `github_pr` / `github_commit` / `github_issue` / `github` / `slack` / `figma` / `other`), `external_issue_relations` (bidirectional — `blocks` creates both A-blocks-B and B-blocked_by-A rows), and `external_project_updates`. The issue upsert also populates `triage_responsibility_team_id` and `triage_auto_assigned` from Linear's `triageResponsibility` field. `sanitize_preview()` strips emails / tokens / UUIDs / SHAs from 280-char previews AND provider-prefixed secrets (GitHub classic + fine-grained PATs `ghp_`/`ghs_`/`gho_`/`ghu_`/`ghr_`/`github_pat_`, Linear API keys `lin_api_`, Anthropic `sk-ant-`, OpenAI `sk-`) without requiring a `Bearer`/`token=`/`api_key=` prefix — placeholder format is `[REDACTED:<provider>]`. Bot detection via Linear's `botActor` field (never email-pattern inference). Per-issue inner pagination emits a `linear.pagination.cap_hit` structured warning if `_MAX_INNER_PAGES` (50) is reached without exhausting `hasNextPage`.
- **PR↔issue linker (Phase 02):** 4-pass cumulative linker in `link_prs_to_external_issues`: Pass 1 = Linear attachments (`github_pr` URLs → PR.id, `high` confidence), Pass 2 = branch regex (`medium`), Pass 3 = title regex (`medium`), Pass 4 = body regex (`low`). Existing links upgrade to higher confidence when a stronger signal arrives. `run_linear_relink()` is the admin-triggerable rerun path (idempotent).
- **AI guards:** All AI call sites check feature toggles → budget → cooldown before calling Claude. `AIFeatureDisabledError` → 403, `AIBudgetExceededError` → 429 (handled globally).
- **AI context enrichment:** 1:1 prep (`build_one_on_one_context`) and team health (`build_team_health_context`) include Linear sprint data when an active integration + developer mapping exists. `gather_sprint_context_for_developer()` adds active sprint, recent sprints, triage stats, estimation patterns. `gather_planning_health_context()` adds velocity trend, completion rate, scope creep, triage health, estimation accuracy, work alignment, at-risk projects. Both return `None` gracefully when Linear is not configured.
- **Encryption:** Shared Fernet in `services/encryption.py` for Slack tokens and Linear API keys. Requires `ENCRYPTION_KEY` env var.
- **Issue tracker integration:** Linear is the primary issue tracker. Generic `integration_config` table (type column) designed for future Jira support. Stats functions branch on `get_primary_issue_source()` to query `issues` (GitHub) or `external_issues` (Linear) table — covers developer stats, team stats, repo stats, issue linkage, issue quality, issue creators, work categorization, work allocation, benchmarks, and trends. `developer_identity_map` links developers to external system accounts. Workload includes `sprint_commitment` context (active sprint progress, on-track status) when Linear is primary.
- **Collaboration scores:** Materialized post-sync from 5 signals (review 0.35, co-author 0.15, issue comments 0.20, mentions 0.15, co-assignment 0.15). Canonical pair ordering (`a_id < b_id`). Co-assignment signal includes Linear sprint co-membership when active (additive — developers in same sprint count as co-assigned).
- **Notifications:** 26 alert types (16 GitHub + 6 planning + 4 PR timeline), dedup by `alert_key`, auto-resolution, per-user read/dismiss tracking with optional expiry. Planning alerts (`velocity_declining`, `scope_creep_high`, `sprint_at_risk`, `triage_queue_growing`, `estimation_accuracy_low`, `linear_sync_failure`) evaluated via `_evaluate_planning_alerts()` — no-op when Linear not configured. Timeline alerts (`pr_review_ping_pong`, `pr_force_push_after_review`, `codeowners_bypassed`, `merge_queue_stuck`) evaluated via `_evaluate_pr_timeline_alerts()` and depend on Phase 09 timeline sync. Issue linkage evaluator branches on primary issue source (`pr_external_issue_links` for Linear, `closes_issue_numbers` for GitHub).
- **Metrics governance (Phase 11):** Every metric surfaced via API registers a `MetricSpec` in `services/metric_spec.py` with category, is_activity flag, `paired_outcome_key` (required when is_activity=True), `visibility_default` (`self` / `team` / `admin`), `is_distribution` (p50+p90 required), and `goodhart_risk`/`goodhart_notes`. Activity metrics missing `paired_outcome_key` raise `ValueError` at import time. `BANNED_METRICS` documents explicitly-excluded metrics (LOC/dev, commit count, individual velocity, TTFR as KPI, raw sentiment per dev). Frontend reads `GET /api/metrics/catalog` for tooltip / pairing / visibility hints. `backend/scripts/generate_metrics_catalog.py` renders the registry to `docs/metrics/catalog.md` — re-run after registry changes.
- **Classifier rules (Phase 10 C3):** `services/classifier_rules.py` backs admin CRUD at `/api/admin/classifier-rules` for three rule kinds (`incident`, `ai_reviewer`, `ai_author`). Incident rule types: `pr_title_prefix`, `revert_detection`, `github_label`, `linear_label`, `linear_issue_type`, `direct_push_no_review` (fires when the caller sets `is_direct_push_to_main=True` and the commit subject doesn't start with any of `DEFAULT_ALLOWED_DIRECT_PUSH_PREFIXES` — admins can override the allowlist via the `pattern` field as a comma-separated list). Patterns are length-capped at `MAX_PATTERN_LENGTH=200` on both create AND update paths; rule types in `REGEX_RULE_TYPES` (currently just `email_pattern`) additionally run through `work_categories._validate_regex_safe` for a nested-quantifier / unbounded-repetition check. DB rows merge on top of hard-coded defaults — they add, never replace.
- **AI-cohort classification (Phase 10):** `services/ai_cohort.py` classifies each PR as `human` / `ai_reviewed` / `ai_authored` / `hybrid` based on configurable reviewer usernames (Copilot, Claude, CodeRabbit, Graphite, Qodo, Sourcery bots), label patterns (`ai-authored`, `copilot`), and commit email patterns. DORA v2 (`services/dora_v2.py`) wraps the existing `get_dora_metrics` to add throughput/stability split, rework rate (7-day same-file follow-up merges), DORA 2024 bands, and per-cohort breakdown. v1 `/api/stats/dora` is preserved unchanged; v2 is at `/api/dora/v2`. When `cohort != "all"`, the top-level `stability.rework_rate` is scoped to that cohort's PR ids; deployment-based metrics (throughput, CFR, MTTR) stay unchanged because Deployment rows carry no cohort signal — the response's `cohort_filter_applied` flag tells the UI which metrics honored the filter. `compute_rework_rate` applies `pr_ids` symmetrically to base + follow-up sides to prevent cross-cohort contamination, and excludes files touched by more than `_REWORK_FILE_POPULARITY_THRESHOLD=20` PRs in the window (package.json, lock files, i18n catalogs) to bound the self-join blast radius.
- **GitHub PR timeline (Phase 09):** `services/github_timeline.py` fetches `timelineItems` via GraphQL (alias-batched up to 50 PRs per request). Batched queries declare `$itemTypes: [PullRequestTimelineItemsItemType!]!` as a single query variable so the 17-item enum list isn't inlined per alias block; node projections use the shared `_TIMELINE_FRAGMENT`. `_fetch_single_batch` enforces rate-limit back-off: preemptive sleep until `resetAt` when `rateLimit.remaining / rateLimit.limit < 10%`, plus one-shot 403 retry honouring `Retry-After` (a second 403 propagates). Persists `pr_timeline_events` rows and derives 9 aggregate columns on `pull_requests`: `force_push_count_after_first_review`, `review_requested_count`, `ready_for_review_at`, `draft_flip_count`, `renamed_title_count`, `dismissed_review_count`, `merge_queue_waited_s`, `auto_merge_waited_s`, `codeowners_bypass`. CODEOWNERS parsing + bypass detection in `services/codeowners.py`. **Not yet wired into `sync_repo`** — standalone entry point until follow-up integration.
- **Logging:** structlog with `event_type` taxonomy. JSON in prod, console in dev. `LoggingContextMiddleware` injects `request_id`.
- **Error handling:** `libs/errors.py` — classifies all exceptions into 8 categories, only reports `app_bug` to Sentinel after frequency threshold.
- **Rate limiting:** slowapi, default 120/min. Disabled via `RATE_LIMIT_ENABLED=false` in tests.

### Frontend

- **State:** TanStack Query (30s stale, 1 retry). JWT in `localStorage` key `devpulse_token`.
- **Styling:** shadcn/ui base-nova, CSS variables, Lucide icons. `sonner` for toasts.
- **Charts:** Recharts 3, `ResponsiveContainer`, CSS vars for colors, `useId()` for SVG gradient IDs.
- **Error handling:** `ErrorCard` + per-section `ErrorBoundary`. `StatCardSkeleton`/`TableSkeleton` for loading.
- **Code splitting:** All pages lazy-loaded via `React.lazy()`.
- **Nav:** Top nav (Dashboard, Executive, Insights, Goals, Admin dropdown). Insights + Admin use `SidebarLayout`. `isNavActive()` uses prefix matching. Insights sidebar is grouped into **People / Delivery / Issues / Planning** (built in `App.tsx` as `insightsSidebarGroups`); `SidebarLayout` accepts either `items` (flat, used by Admin) or `groups` (used by Insights). The `Planning` group holds Linear-only pages; when Linear isn't configured it collapses to a single "Sprint Planning ›" setup CTA pointing at `/admin/integrations`. `Conversations` (inside the `Issues` group) is also Linear-gated.
- **Date range:** Global `DateRangeContext` in Layout header, consumed by all pages.
- **Trend deltas:** Current vs previous period. For lower-is-better metrics, green = decrease.
- **AI rendering:** `components/ai/` — structured views for AI analysis output. `AnalysisResultRenderer` dispatches by analysis type to `GenericAnalysisView` (general), `OneOnOnePrepView` (1:1 prep briefs), or `TeamHealthView` (team health). Each renders Claude API JSON as themed card layouts with sections, recommendations, and metrics.
- **Metrics governance UI (Phase 11 + wiring):** `MetricsUsageBanner` renders at the top of every metric-surface route (Dashboard, ExecutiveDashboard, all `/insights/*` via SidebarLayout, `/admin/linkage-quality`, `/admin/metrics-governance`, `/admin/classifier-rules`) — the banner's quarterly-dismiss state is shared via localStorage so render-site duplication is cost-free. `DistributionStatCard` (p50 + p90 + optional histogram) replaces bare averages wherever p50/p90 is available from the backend — wired on FlowAnalytics (per-status time distribution) and Bottlenecks (cycle-time histogram). `AiCohortBadge` is the disclosure chip on DoraMetrics when the AI-touched share > 0 (replaces hand-built inline Badge). `StatCard` accepts a `pairedOutcome={{ label, value, tooltip }}` slot — activity metrics (PR count, review count) pair with an outcome (merge rate, time-to-first-review) so throughput can't be read without quality. Wired on Dashboard "Total PRs" + "Total Reviews" and DeveloperDetail "PRs Opened".
- **Linear Insights v2 pages:** `/insights/conversations` (Phase 04), `/insights/flow` (Phase 06), `/insights/bottlenecks` (Phase 07) sidebar entries gated on `hasLinear` via `useMemo` on `linearInsightsSidebarItems`. Sub-queries on those pages also pass `{ enabled: !!hasLinear }` to every Linear-scoped hook in `useConversations.ts` / `useFlowAnalytics.ts` / `useBottlenecks.ts` so non-Linear installs issue zero Linear-scoped network requests on mount. `/admin/linkage-quality` (Phase 02) in admin sidebar. Dashboard `LinearUsageHealthCard` renders only when Linear is primary (hides on 409 from `/api/linear/usage-health`). DeveloperDetail has 3 stacked `<h2>` sections (Creator / Worker / Shepherd) after the Active Sprint Card — Creator + Shepherd gated on `isAdmin || isOwnPage`; Worker is peer-visible (any authenticated user) when Linear is primary, matching the spec that Worker signals are team-visible while Creator + Shepherd are privileged.

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
