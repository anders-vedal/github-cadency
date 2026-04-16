---
Status: Planned
Priority: High
Type: Infrastructure
Apps: backend, frontend
Effort: Medium
Linear: NOR-1125
---

# E2E Playwright Test Infrastructure for DevPulse

## Summary

Introduce a self-contained Playwright E2E test suite that exercises DevPulse from the browser through the FastAPI backend to PostgreSQL. The goal is fast, reliable CI feedback on critical user flows — health, authentication, dashboard rendering, and insight pages — without touching the existing unit-test suite or deploy workflow.

The implementation is split into three independently deliverable sub-tasks:

1. **01-scaffolding-and-config** — `e2e/` directory, Docker Compose isolation, seed script, global setup, stub PEM, `.gitignore` additions.
2. **02-tests-and-page-objects** — Playwright fixtures, page objects, smoke tests, insight tests.
3. **03-ci-integration** — GitHub Actions workflow `e2e.yml` with service containers, artifact upload, and environment secrets.

## Research Findings

- `GET /api/health` returns `{"status": "ok"}` — defined at `backend/app/main.py:586-588`. No auth required.
- JWT issued by `create_jwt()` at `backend/app/api/auth.py:20-36`. Signature: `create_jwt(developer_id, github_username, app_role, token_version=1) -> str`. Uses `settings.jwt_secret` (must be ≥32 chars — enforced by `backend/app/config.py:87-91`).
- Frontend stores JWT in `localStorage` under key `devpulse_token` (`frontend/src/App.tsx:103`).
- `ProtectedRoute` (App.tsx:102-117) redirects to `/login` when token is absent or user fails to load.
- Admin users land at `/` (Dashboard); non-admin users are redirected to `/team/:id` (App.tsx:150).
- Non-admin users are redirected away from `/insights/*` (App.tsx:181).
- Login page renders `"DevPulse"` heading and `"Login with GitHub"` button (`frontend/src/pages/Login.tsx`).
- Already-authenticated visits to `/login` redirect to `/` (Login.tsx:12-14).
- `Developer` model has `app_role`, `token_version`, `is_active` columns (`backend/app/models/models.py:41-43`).
- `RoleDefinition` at models.py:1176, `Team` at models.py:780 — both must exist before developers can reference them.
- `RATE_LIMIT_ENABLED=false` disables slowapi in tests (`backend/app/config.py:58`).
- The existing deploy workflow is at `.github/workflows/deploy.yml` — the E2E workflow must be a separate file.
- Production Docker Compose uses port 5433 for Postgres and 8000/3001 for backend/frontend. E2E stack uses 5434/8001/5174 to avoid collisions.
- Existing backend scripts pattern: `backend/scripts/recompute_review_quality.py` — run via `python -m scripts.<name>` from `backend/`.
- Alembic config lives at `backend/migrations/` with async env; migrations invoked via `alembic upgrade head` from `backend/`.

## Architecture

```
e2e/                         # Playwright workspace (standalone npm package)
├── package.json             # @playwright/test dependency
├── tsconfig.json
├── playwright.config.ts     # baseURL, projects, webServer (local only), globalSetup
├── global-setup.ts          # Runs e2e_seed.py, writes storageState JSON files
├── fixtures/
│   ├── auth.ts              # adminPage / developerPage fixtures
│   └── stub-github-app.pem  # Dummy RSA PEM for backend startup validation
├── pages/                   # Page Object Models
│   ├── LoginPage.ts
│   ├── DashboardPage.ts
│   └── InsightsPage.ts
├── tests/
│   ├── smoke/               # chromium-smoke project — no storageState
│   │   ├── health.spec.ts
│   │   ├── auth.spec.ts
│   │   └── dashboard.spec.ts
│   └── insights/            # chromium project — authenticated
│       └── workload.spec.ts
└── playwright/
    └── .auth/               # gitignored — written by global-setup.ts
        ├── admin.json
        └── developer.json

backend/scripts/e2e_seed.py  # Seed + JWT generation script

docker-compose.e2e.yml       # Isolated stack (ports 5434, 8001, 5174)
.env.e2e.example             # Committed env template

.github/workflows/e2e.yml    # Separate CI workflow — never merged into deploy.yml
```

**Data flow in CI:**
1. GitHub Actions spins up a `postgres:15.17` service container.
2. Backend deps installed, `alembic upgrade head` runs migrations.
3. Backend started via `uvicorn` in background; health-check polled.
4. Frontend started via `pnpm dev` in background; port polled.
5. `e2e_seed.py` inserts developers, prints JWT JSON.
6. `global-setup.ts` writes `playwright/.auth/{admin,developer}.json`.
7. Playwright smoke suite (PRs) or full chromium suite (main) executes.
8. Reports and traces uploaded as artifacts.

## Security Considerations

- **Secrets in CI:** `E2E_JWT_SECRET` and `E2E_ENCRYPTION_KEY` are stored as GitHub Actions secrets, never hardcoded. They must not appear in workflow logs.
- **Isolated database:** E2E PostgreSQL is a separate volume (`pgdata_e2e`) and port (5434) — no risk of contaminating the development or production database.
- **Stub PEM:** `e2e/fixtures/stub-github-app.pem` is a dummy RSA key committed to the repo solely to satisfy the backend's file-existence check. It is never used for actual GitHub App authentication. The file must begin with `-----BEGIN RSA PRIVATE KEY-----` (or `-----BEGIN PRIVATE KEY-----`) to pass `config.py:validate_github_config()` content check.
- **Gitignored auth files:** `e2e/playwright/.auth/` contains JWTs written at runtime — they must never be committed.
- **RATE_LIMIT_ENABLED=false:** Disables slowapi in the E2E environment to avoid test flakiness from rate-limit false positives.
- **Read-only tests:** Tests never write to GitHub, Linear, or the production database. All test operations are idempotent reads against the seeded E2E database.
- **Token expiry:** JWTs have a 4-hour expiry (`backend/app/api/auth.py:17`). CI runs complete well within this window; no refresh logic is required.

## Scope

### v1 (this feature)

- `e2e/` directory with Playwright config, fixtures, page objects, and tests.
- `backend/scripts/e2e_seed.py` — synchronous seed with async SQLAlchemy via `asyncio.run()`.
- `docker-compose.e2e.yml` for local isolated stack.
- `.env.e2e.example` committed template.
- `e2e/fixtures/stub-github-app.pem` dummy RSA key.
- Smoke tests: `/api/health`, unauthenticated redirect, login page render, authenticated redirect from `/login`.
- Insight tests: workload page admin access, non-admin redirect.
- GitHub Actions `e2e.yml` with artifact upload.

### Deferred

- Firefox and WebKit browser coverage (config stubs included but not wired to CI).
- Visual regression testing (screenshot diffing).
- API contract tests beyond the health endpoint.
- Mobile viewport tests.
- Accessibility (a11y) assertions.
- Test coverage for sync wizard, AI analysis, and admin settings flows.
- Playwright component tests for React components in isolation.
