# Task 01: Project Scaffolding & Infrastructure

## Phase
Phase 1 — Data Foundation

## Status
completed

## Blocked By
None (starting task)

## Blocks
- 02-sqlalchemy-models
- 10-frontend-scaffold

## Description
Create the full directory structure per spec Section 9 and set up all foundational tooling.

## Deliverables

### Directory structure
```
devpulse/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, lifespan, middleware
│   │   ├── config.py            # pydantic-settings config
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── developers.py
│   │   │   ├── stats.py
│   │   │   ├── ai_analysis.py
│   │   │   ├── sync.py
│   │   │   └── webhooks.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   └── database.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── github_sync.py
│   │   │   ├── stats.py
│   │   │   └── ai_analysis.py
│   │   └── schemas/
│   │       ├── __init__.py
│   │       └── schemas.py
│   ├── migrations/
│   ├── requirements.txt
│   └── alembic.ini
├── frontend/                     # Vite + React 18 + TypeScript
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml            # PostgreSQL 15 + backend + frontend
├── .env.example
├── CLAUDE.md
└── README.md
```

### backend/app/main.py
- FastAPI app with lifespan (startup/shutdown)
- CORS middleware
- Router includes for all API modules (stubbed)
- `/api/health` endpoint

### backend/app/config.py
- pydantic-settings `Settings` class with all env vars from spec Section 8:
  - DATABASE_URL, GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_PATH, GITHUB_APP_INSTALLATION_ID
  - GITHUB_WEBHOOK_SECRET, GITHUB_ORG, DEVPULSE_ADMIN_TOKEN, ANTHROPIC_API_KEY
  - SYNC_INTERVAL_MINUTES (default 15), FULL_SYNC_CRON_HOUR (default 2)

### backend/requirements.txt
- fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic
- pydantic-settings, httpx, anthropic, apscheduler
- python-multipart, python-jose (for future auth)

### docker-compose.yml
- PostgreSQL 15 service with volume persistence
- Backend service (uvicorn)
- Frontend service (vite dev server)

### .env.example
- All config vars from Section 8 with placeholder values

### Alembic
- `alembic init` with async template
- Configure alembic.ini and env.py to use DATABASE_URL from config

### CLAUDE.md
- Project overview, tech stack, how to run, key conventions
