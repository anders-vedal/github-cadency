---
purpose: "High-level architecture, deployment topology, invariants, and component map"
last-updated: "2026-03-29"
related:
  - docs/architecture/DATA-MODEL.md
  - docs/architecture/API-DESIGN.md
  - docs/architecture/SERVICE-LAYER.md
  - docs/architecture/FRONTEND.md
  - docs/architecture/DATA-FLOWS.md
---

# Architecture Overview

## System Diagram

```
                          GitHub REST API (read-only)
                                 ^  |
                    JWT auth     |  | webhooks + sync fetches
                                 |  v
  React Frontend  --/api-->  FastAPI Backend  <-->  PostgreSQL
    (Vite :5173)             (:8000)                (:5432)
                                 |
                                 v
                          Claude API (on-demand)
```

## Core Invariants

1. **AI is off by default** -- all stats are deterministic from raw data
2. **GitHub is the single source of truth** -- DevPulse never writes back
3. **All GitHub data is cached locally** in PostgreSQL to handle rate limits
4. **All backend I/O is async** -- SQLAlchemy async sessions, httpx.AsyncClient

## Tech Stack

See [CLAUDE.md](../../CLAUDE.md) for the full tech stack reference. Key components:

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Alembic |
| Database | PostgreSQL 15+ via asyncpg |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui, TanStack Query v5 |
| GitHub | REST API via httpx, GitHub App auth (JWT + installation tokens) |
| AI | Anthropic Claude API (claude-sonnet-4-0), on-demand only |
| Slack | slack_sdk AsyncWebClient, bot token stored in DB |
| Scheduling | APScheduler AsyncIOScheduler (in-process, FastAPI lifespan) |

## Deployment Topology

Docker Compose runs three containers: `backend` (:8000), `frontend` (:3001 proxying to :5173), `db` (:5432). The frontend Vite dev server proxies `/api/*` to the backend. No reverse proxy, message queue, or external cache.

## Component Map

| Component | Docs |
|-----------|------|
| 21 database tables, JSONB columns, nullable FK pattern | [DATA-MODEL.md](DATA-MODEL.md) |
| 9 API routers, auth model, error handling | [API-DESIGN.md](API-DESIGN.md) |
| 11 services: sync, stats, collaboration, enhanced collaboration, relationships, risk, goals, AI, work categorization, AI settings, Slack | [SERVICE-LAYER.md](SERVICE-LAYER.md) |
| React pages, hooks, state management, design system | [FRONTEND.md](FRONTEND.md) |
| End-to-end flows: sync, webhooks, stats, AI, auth, goals | [DATA-FLOWS.md](DATA-FLOWS.md) |

## Backend Structure

```
backend/app/
├── api/           # 8 routers (thin delegation to services)
├── models/        # database.py (engine, sessions), models.py (18 ORM models)
├── schemas/       # schemas.py (70+ Pydantic models, enums)
├── services/      # 10 service modules (all business logic)
├── config.py      # pydantic-settings (env vars)
└── main.py        # App factory, CORS, router registration, APScheduler lifespan
```

## Frontend Structure

```
frontend/src/
├── pages/         # Route components + insights/ + sync/ + settings/ sub-pages
├── components/    # Layout, SidebarLayout, StatCard, charts/, ai/, ui/ (shadcn)
├── hooks/         # TanStack Query hooks (auth, stats, sync, AI, goals, date range)
├── utils/         # api.ts (apiFetch), types.ts (TS interfaces)
└── lib/           # cn() utility
```

## Data Flow Summary

1. **Sync**: Scheduled or API-triggered -> fetches repos/PRs/reviews/issues from GitHub -> upserts to PostgreSQL -> backfills author FKs
2. **Webhooks**: Real-time GitHub events -> HMAC verified -> upserted to DB
3. **Stats**: On-demand computation from cached data -> returned as Pydantic models
4. **AI**: Guard checks (toggle/budget/cooldown) -> gather data -> Claude API -> store result

See [DATA-FLOWS.md](DATA-FLOWS.md) for step-by-step traces with `file:function` references.

## Architectural Concerns

| Severity | Area | Description |
|----------|------|-------------|
| ~~High~~ | ~~Migrations~~ | ~~No initial migration~~ — **Fixed**: `000_initial_schema.py` added |
| ~~High~~ | ~~Auth~~ | ~~No JWT revocation -- deactivated users retain access for up to 7 days~~ — **Fixed**: `get_current_user()` checks `developers.is_active` on every request |
| Medium | Sync | Auto-reactivation in sync can undo manual deactivation if the developer appears in GitHub activity or org members (warning log only) |
| Medium | Sync | TOCTOU race on sync start -- three optimistic reads without DB-level locking |
| Medium | Stats | N+1 query pattern in benchmarks -- ~9 queries per developer in Python loop |
| Medium | Frontend | Single global ErrorBoundary -- any page crash takes down the entire UI |
| ~~Medium~~ | ~~API~~ | ~~Latent `NameError` in `sync.py` -- uses `httpx.HTTPStatusError` without importing `httpx`~~ — **Fixed**: `import httpx` added |
| Low | Services | `_default_range()` duplicated in 5 service files |
