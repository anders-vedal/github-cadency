---
Status: Planned
Priority: High
Type: Infrastructure
Apps: backend, frontend
Effort: Medium
Linear: NOR-1125
---

# Sub-task 1: Scaffolding and Configuration

Set up the foundational E2E infrastructure: workspace directory, Playwright config, isolated Docker Compose stack, backend seed script, global setup, stub PEM, and gitignore additions. No tests are written in this sub-task — only the skeleton that subsequent sub-tasks depend on.

## What to Build

### 1. `e2e/package.json`

```json
{
  "name": "devpulse-e2e",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "test": "playwright test",
    "test:smoke": "playwright test --project=chromium-smoke",
    "report": "playwright show-report"
  },
  "devDependencies": {
    "@playwright/test": "^1.50.0",
    "typescript": "^5.8.0"
  }
}
```

### 2. `e2e/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "moduleResolution": "node",
    "strict": true,
    "esModuleInterop": true,
    "outDir": "./dist",
    "rootDir": ".",
    "paths": {}
  },
  "include": ["**/*.ts"],
  "exclude": ["node_modules", "dist", "playwright-report", "test-results"]
}
```

### 3. `e2e/playwright.config.ts`

Key settings:
- `testDir`: `./tests`
- `fullyParallel`: `true`
- `forbidOnly`: `!!process.env.CI`
- `retries`: `process.env.CI ? 2 : 0`
- `workers`: `process.env.CI ? 2 : undefined`
- `reporter`: `[['html', { open: 'never' }], ['list']]`
- `globalSetup`: `'./global-setup.ts'`
- `use.baseURL`: `'http://localhost:5173'`
- `use.trace`: `'on-first-retry'`
- `use.screenshot`: `'only-on-failure'`

Projects:
```
chromium-smoke  — { name: 'chromium-smoke', use: { ...devices['Desktop Chrome'] }, testMatch: '**/smoke/**/*.spec.ts' }
chromium        — { name: 'chromium', use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/admin.json' }, testMatch: '**/!(smoke)/**/*.spec.ts', dependencies: ['chromium-smoke'] }
```

`webServer` array (only when `!process.env.CI`):
```typescript
webServer: process.env.CI ? undefined : [
  {
    command: 'cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000',
    url: 'http://localhost:8000/api/health',
    reuseExistingServer: true,
    timeout: 60_000,
    env: { /* see .env.e2e.example */ },
  },
  {
    command: 'cd ../frontend && pnpm dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
],
```

### 4. `.env.e2e.example` (committed to repo root)

```dotenv
# E2E environment — copy to .env.e2e and fill in values
# Never commit .env.e2e

# Database (E2E-isolated, port 5434)
DATABASE_URL=postgresql+asyncpg://devpulse:devpulse@localhost:5434/devpulse_e2e

# Auth — must be >=32 chars (config.py exits on startup if shorter)
JWT_SECRET=e2e-test-secret-replace-this-with-at-least-32-chars

# Encryption key (Fernet — generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=

# GitHub App — stub values so backend starts without real credentials
GITHUB_APP_ID=1
GITHUB_APP_INSTALLATION_ID=1
GITHUB_APP_PRIVATE_KEY_PATH=../e2e/fixtures/stub-github-app.pem
GITHUB_ORG=e2e-test-org
GITHUB_WEBHOOK_SECRET=e2e-webhook-secret

# Disable rate limiting in tests
RATE_LIMIT_ENABLED=false

# Frontend URL (used for CORS)
FRONTEND_URL=http://localhost:5174

# Logging
LOG_FORMAT=console
LOG_LEVEL=WARNING
```

### 5. `docker-compose.e2e.yml` (repo root)

```yaml
# Isolated E2E stack — does not share volumes or ports with the main compose stack.
# Usage: docker compose -f docker-compose.e2e.yml up -d

services:
  db-e2e:
    image: postgres:15.17
    environment:
      POSTGRES_USER: devpulse
      POSTGRES_PASSWORD: devpulse
      POSTGRES_DB: devpulse_e2e
    ports:
      - "127.0.0.1:5434:5432"
    volumes:
      - pgdata_e2e:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U devpulse"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend-e2e:
    build:
      context: ./backend
    ports:
      - "8001:8000"
    env_file:
      - .env.e2e
    environment:
      DATABASE_URL: postgresql+asyncpg://devpulse:devpulse@db-e2e:5432/devpulse_e2e
      RATE_LIMIT_ENABLED: "false"
      LOG_FORMAT: console
      GITHUB_APP_PRIVATE_KEY_PATH: /etc/devpulse/stub-github-app.pem
    volumes:
      - ./e2e/fixtures/stub-github-app.pem:/etc/devpulse/stub-github-app.pem:ro
    depends_on:
      db-e2e:
        condition: service_healthy

  frontend-e2e:
    build:
      context: ./frontend
    ports:
      - "5174:5173"
    environment:
      CI: "true"
      API_URL: http://backend-e2e:8000
    depends_on:
      - backend-e2e

volumes:
  pgdata_e2e:
```

### 6. `backend/scripts/e2e_seed.py`

This script:
1. Connects to the E2E PostgreSQL database using `DATABASE_URL` from the environment.
2. Runs `Base.metadata.create_all()` synchronously — idempotent, safe to re-run.
3. Upserts a `Team` row (name=`"e2e-team"`).
4. Upserts a `RoleDefinition` row (role_key=`"engineer"`, display_name=`"Engineer"`, contribution_category=`"code_contributor"`).
5. Upserts an admin `Developer` (github_username=`"e2e-admin"`, display_name=`"E2E Admin"`, app_role=`"admin"`, team=`"e2e-team"`, role=`"engineer"`).
6. Upserts a developer `Developer` (github_username=`"e2e-dev"`, display_name=`"E2E Developer"`, app_role=`"developer"`, team=`"e2e-team"`, role=`"engineer"`).
7. Calls `create_jwt()` for both developers.
8. Prints JSON to stdout: `{"admin_token": "...", "developer_token": "..."}`.

Implementation pattern (follow `backend/scripts/recompute_review_quality.py` as style reference):

```python
"""Seed E2E database and output JWT tokens for Playwright global setup.

Usage (from repo root):
    DATABASE_URL=postgresql+asyncpg://... JWT_SECRET=... python -m scripts.e2e_seed

Outputs JSON to stdout:
    {"admin_token": "<jwt>", "developer_token": "<jwt>"}
"""

import asyncio
import json
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# DATABASE_URL must point at the E2E database before importing app.config
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://devpulse:devpulse@localhost:5434/devpulse_e2e")

from app.api.auth import create_jwt
from app.models.database import Base
from app.models.models import Developer, RoleDefinition, Team


async def seed() -> dict:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as db:
        # Upsert Team
        team_result = await db.execute(select(Team).where(Team.name == "e2e-team"))
        team = team_result.scalar_one_or_none()
        if not team:
            team = Team(name="e2e-team", display_order=0)
            db.add(team)
            await db.flush()

        # Upsert RoleDefinition
        role_result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "engineer"))
        role_def = role_result.scalar_one_or_none()
        if not role_def:
            role_def = RoleDefinition(
                role_key="engineer",
                display_name="Engineer",
                contribution_category="code_contributor",
                display_order=0,
                is_default=True,
            )
            db.add(role_def)
            await db.flush()

        # Upsert admin developer
        admin_result = await db.execute(select(Developer).where(Developer.github_username == "e2e-admin"))
        admin = admin_result.scalar_one_or_none()
        if not admin:
            admin = Developer(
                github_username="e2e-admin",
                display_name="E2E Admin",
                app_role="admin",
                team="e2e-team",
                role="engineer",
                token_version=1,
                is_active=True,
            )
            db.add(admin)
        else:
            admin.app_role = "admin"
            admin.is_active = True
        await db.flush()

        # Upsert regular developer
        dev_result = await db.execute(select(Developer).where(Developer.github_username == "e2e-dev"))
        dev = dev_result.scalar_one_or_none()
        if not dev:
            dev = Developer(
                github_username="e2e-dev",
                display_name="E2E Developer",
                app_role="developer",
                team="e2e-team",
                role="engineer",
                token_version=1,
                is_active=True,
            )
            db.add(dev)
        else:
            dev.app_role = "developer"
            dev.is_active = True
        await db.flush()

        await db.commit()

        admin_token = create_jwt(
            developer_id=admin.id,
            github_username=admin.github_username,
            app_role=admin.app_role,
            token_version=admin.token_version,
        )
        dev_token = create_jwt(
            developer_id=dev.id,
            github_username=dev.github_username,
            app_role=dev.app_role,
            token_version=dev.token_version,
        )

    await engine.dispose()
    return {"admin_token": admin_token, "developer_token": dev_token}


if __name__ == "__main__":
    result = asyncio.run(seed())
    print(json.dumps(result))
```

### 7. `e2e/global-setup.ts`

```typescript
import { execSync } from 'child_process'
import * as fs from 'fs'
import * as path from 'path'

const AUTH_DIR = path.join(__dirname, 'playwright', '.auth')

export default async function globalSetup() {
  fs.mkdirSync(AUTH_DIR, { recursive: true })

  const output = execSync(
    'python -m scripts.e2e_seed',
    {
      cwd: path.join(__dirname, '..', 'backend'),
      env: { ...process.env },
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'inherit'],  // pass stderr through for diagnostics
    }
  )

  const { admin_token, developer_token } = JSON.parse(output.trim())

  const makeStorageState = (token: string) => ({
    cookies: [],
    origins: [
      {
        origin: 'http://localhost:5173',
        localStorage: [
          { name: 'devpulse_token', value: token },
        ],
      },
    ],
  })

  fs.writeFileSync(
    path.join(AUTH_DIR, 'admin.json'),
    JSON.stringify(makeStorageState(admin_token), null, 2)
  )
  fs.writeFileSync(
    path.join(AUTH_DIR, 'developer.json'),
    JSON.stringify(makeStorageState(developer_token), null, 2)
  )

  console.log('[global-setup] storageState files written to', AUTH_DIR)
}
```

### 8. `e2e/fixtures/stub-github-app.pem`

Generate with:
```bash
openssl genrsa -out e2e/fixtures/stub-github-app.pem 2048
```

This is a dummy 2048-bit RSA key committed to the repo. It exists solely to pass the `validate_github_config()` file-existence and `-----BEGIN` content checks in `backend/app/config.py:162-169`. It is never used for actual GitHub App JWT signing because E2E tests never call the GitHub API.

### 9. `.gitignore` additions (append to repo root `.gitignore`)

```gitignore
# E2E Playwright
e2e/.env.e2e
e2e/playwright/.auth/
e2e/playwright-report/
e2e/test-results/
e2e/node_modules/
```

## Implementation Notes

- **`create_jwt` import:** The function is a plain synchronous function at `backend/app/api/auth.py:20-36`. It reads `settings.jwt_secret` from `app.config.settings`. Ensure `JWT_SECRET` env var is set before importing any `app.*` module — the config module raises `SystemExit` if it is missing or shorter than 32 chars (`backend/app/config.py:87-91`).
- **`Base.metadata.create_all` vs Alembic:** The seed script uses `create_all` for simplicity. In CI, `alembic upgrade head` runs first (see sub-task 03), so `create_all` in the seed is a no-op safety net. Do not remove the `alembic upgrade head` CI step.
- **`Team` FK constraint:** `Developer.team` is a FK to `teams.name` (`backend/app/models/models.py:39`). The `Team` row must be inserted before the `Developer` rows, or the FK constraint will reject the insert.
- **`RoleDefinition` is not FK-constrained to `Developer.role`:** The `role` column on `Developer` is `String(50)` with no FK constraint — it is a free-form label. Upserting `RoleDefinition` is done so the frontend role-based filters return meaningful data, not because of a schema requirement.
- **Sync vs async seed script:** The seed script uses `asyncio.run()` to drive async SQLAlchemy. This matches the pattern in `backend/scripts/recompute_review_quality.py`. Run it from `backend/` so relative imports resolve correctly.
- **`webServer` in `playwright.config.ts`:** Set `reuseExistingServer: true` so running `npx playwright test` locally against an already-running stack does not try to start a second server.
- **`playwright.config.ts` globalSetup path:** Must be relative to the config file, so `'./global-setup.ts'` is correct.
- **Chromium-smoke project has no `storageState`:** It relies on the browser's default empty state to test unauthenticated flows.
- **Chromium project `storageState`:** Points to `'playwright/.auth/admin.json'` (relative to the `e2e/` root, which is where the config lives). Tests that need the developer role must load the fixture manually (see sub-task 02).

## Acceptance Criteria

- [ ] `cd e2e && npm install` exits 0 and produces `node_modules/@playwright/test`.
- [ ] `cd e2e && npx playwright install chromium --with-deps` exits 0.
- [ ] `docker compose -f docker-compose.e2e.yml up -d` starts three containers (`db-e2e`, `backend-e2e`, `frontend-e2e`) and all pass health checks.
- [ ] `DATABASE_URL=postgresql+asyncpg://devpulse:devpulse@localhost:5434/devpulse_e2e JWT_SECRET=e2e-test-secret-replace-this-with-at-least-32-chars python -m scripts.e2e_seed` (run from `backend/`) outputs valid JSON with `admin_token` and `developer_token` keys.
- [ ] `e2e/playwright/.auth/admin.json` and `developer.json` are written by global-setup.ts and contain a `localStorage` entry with `devpulse_token`.
- [ ] `e2e/fixtures/stub-github-app.pem` begins with `-----BEGIN RSA PRIVATE KEY-----`.
- [ ] `.gitignore` contains all five E2E paths listed above.
- [ ] Re-running the seed script is idempotent — no duplicate-key errors, tokens are refreshed.

## Tests Required

No Playwright tests are written in this sub-task. The seed script should have a manual smoke test:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://devpulse:devpulse@localhost:5434/devpulse_e2e \
JWT_SECRET=e2e-test-secret-replace-this-with-at-least-32-chars \
python -m scripts.e2e_seed
# Expected: {"admin_token": "eyJ...", "developer_token": "eyJ..."}
```

Verify idempotency by running twice — second run must produce the same JSON structure without errors.
