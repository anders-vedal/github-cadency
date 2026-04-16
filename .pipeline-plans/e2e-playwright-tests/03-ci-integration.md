---
Status: Planned
Priority: High
Type: Infrastructure
Apps: backend, frontend
Effort: Small
Linear: NOR-1125
---

# Sub-task 3: CI Integration

Create the GitHub Actions workflow that runs Playwright E2E tests in CI. This sub-task depends on both sub-task 01 (scaffolding) and sub-task 02 (tests) being merged first.

## What to Build

### 1. `.github/workflows/e2e.yml`

This is a new, standalone workflow file. It must NOT be merged into `.github/workflows/deploy.yml`.

```yaml
name: E2E Tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    services:
      postgres:
        image: postgres:15.17
        env:
          POSTGRES_USER: devpulse
          POSTGRES_PASSWORD: devpulse
          POSTGRES_DB: devpulse_e2e
        ports:
          - 5434:5432
        options: >-
          --health-cmd "pg_isready -U devpulse"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    env:
      # Backend env — passed to all steps that invoke Python
      DATABASE_URL: postgresql+asyncpg://devpulse:devpulse@localhost:5434/devpulse_e2e
      JWT_SECRET: ${{ secrets.E2E_JWT_SECRET }}
      ENCRYPTION_KEY: ${{ secrets.E2E_ENCRYPTION_KEY }}
      RATE_LIMIT_ENABLED: "false"
      LOG_FORMAT: console
      LOG_LEVEL: WARNING
      GITHUB_APP_ID: "1"
      GITHUB_APP_INSTALLATION_ID: "1"
      GITHUB_APP_PRIVATE_KEY_PATH: ${{ github.workspace }}/e2e/fixtures/stub-github-app.pem
      GITHUB_ORG: e2e-test-org
      GITHUB_WEBHOOK_SECRET: e2e-webhook-secret-ci
      FRONTEND_URL: http://localhost:5173

    steps:
      - uses: actions/checkout@v4

      # --- Python / Backend ---

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install backend dependencies
        run: |
          cd backend
          pip install -r requirements.txt

      - name: Run Alembic migrations
        run: |
          cd backend
          alembic upgrade head

      - name: Start backend server
        run: |
          cd backend
          uvicorn app.main:app --host 0.0.0.0 --port 8000 &
          echo "BACKEND_PID=$!" >> "$GITHUB_ENV"

      - name: Wait for backend health check
        run: |
          echo "Waiting for backend at http://localhost:8000/api/health ..."
          for i in $(seq 1 30); do
            if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
              echo "Backend is ready (attempt $i)"
              exit 0
            fi
            echo "Attempt $i/30 — backend not ready yet, sleeping 2s"
            sleep 2
          done
          echo "Backend did not become healthy within 60s"
          exit 1

      # --- Node / Frontend ---

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Enable pnpm via corepack
        run: corepack enable pnpm

      - name: Install frontend dependencies
        run: |
          cd frontend
          pnpm install --frozen-lockfile

      - name: Start frontend dev server
        run: |
          cd frontend
          pnpm dev &
          echo "FRONTEND_PID=$!" >> "$GITHUB_ENV"
        env:
          VITE_API_URL: http://localhost:8000

      - name: Wait for frontend
        run: |
          echo "Waiting for frontend at http://localhost:5173 ..."
          for i in $(seq 1 30); do
            if curl -sf http://localhost:5173 > /dev/null 2>&1; then
              echo "Frontend is ready (attempt $i)"
              exit 0
            fi
            echo "Attempt $i/30 — frontend not ready yet, sleeping 2s"
            sleep 2
          done
          echo "Frontend did not become available within 60s"
          exit 1

      # --- E2E ---

      - name: Install Playwright dependencies
        run: |
          cd e2e
          npm ci

      - name: Install Playwright browsers
        run: |
          cd e2e
          npx playwright install chromium --with-deps

      # Note: global-setup.ts (configured in playwright.config.ts) handles both
      # DB seeding and storageState file generation before tests run.
      # No explicit seed step needed here.

      - name: Run smoke tests (pull_request)
        if: github.event_name == 'pull_request'
        run: |
          cd e2e
          npx playwright test --project=chromium-smoke

      - name: Run full E2E suite (push to main)
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          cd e2e
          npx playwright test --project=chromium

      # --- Artifacts ---

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: e2e/playwright-report/
          retention-days: 14

      - name: Upload test results on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: e2e/test-results/
          retention-days: 7
```

### 2. Required GitHub Actions Secrets

Add the following secrets to the repository (Settings > Secrets and variables > Actions):

| Secret Name | Description | How to generate |
|---|---|---|
| `E2E_JWT_SECRET` | JWT signing secret for E2E backend. Must be ≥32 chars. | `openssl rand -hex 32` |
| `E2E_ENCRYPTION_KEY` | Fernet key for `services/encryption.py`. Required for backend startup when `ENCRYPTION_KEY` is set. | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

Both secrets are scoped to E2E only — they must not be the same values used in the production environment.

## Implementation Notes

- **No docker-compose in CI:** GitHub Actions service containers (`services.postgres`) are used instead of `docker-compose.e2e.yml`. The E2E compose file is only for local development.
- **Service container port mapping:** The Postgres service container maps `5434:5432` on the runner host, matching `DATABASE_URL` in the workflow `env` block.
- **Backend health polling:** The health check loop uses `curl -sf` against `GET /api/health` (`backend/app/main.py:586-588`). 30 attempts × 2 second sleep = 60 seconds maximum. This is sufficient for uvicorn startup on GitHub-hosted runners.
- **Frontend health polling:** Same pattern — polls `http://localhost:5173`. Vite dev server starts within ~10 seconds on the runner.
- **`GITHUB_APP_PRIVATE_KEY_PATH`:** Points to `${{ github.workspace }}/e2e/fixtures/stub-github-app.pem` — the stub PEM committed in sub-task 01. This satisfies `validate_github_config()` without a real GitHub App.
- **PR vs push branch logic:**
  - `pull_request` → `--project=chromium-smoke` (smoke only — fast feedback, ~3-5 min including setup).
  - `push` to `main` → `--project=chromium` (full authenticated suite including insight tests).
  - This avoids slow full-suite runs on every PR while still giving comprehensive coverage on merged commits.
- **`globalSetup` in CI:** `playwright.config.ts` runs `global-setup.ts` before any test, which calls `python -m scripts.e2e_seed` AND writes the storageState files. This is the single entry point for seeding in both local and CI environments — no separate CI seed step is needed. The `globalSetup` approach ensures seeding and storageState are always in sync.
- **`npm ci` vs `npm install`:** Use `npm ci` in CI for reproducible installs from `package-lock.json`. Run `npm install` locally to generate/update `package-lock.json` before committing.
- **`--with-deps` for Playwright browsers:** Required on GitHub-hosted runners to install system dependencies (libglib, libX11, etc.). Without it, Playwright will fail to launch Chromium.
- **Artifact paths are relative to workspace root:** `e2e/playwright-report/` and `e2e/test-results/` are correct paths from the repo root.
- **`timeout-minutes: 20`:** Should be sufficient. Breakdown: Postgres service startup (~10s), Python install (~30s), backend install (~60s), migrations (~5s), backend start (~5s), Node install (~30s), frontend install (~60s), frontend start (~10s), Playwright install (~30s), Chromium install (~60s), seed (~5s), tests (~2-5 min). Total: ~6-8 min for smoke, ~10-12 min for full suite.
- **Workflow does not call `deploy.yml`:** The two workflows are completely independent. `deploy.yml` runs unit tests on push to main; `e2e.yml` runs E2E tests on both PR and push to main.
- **`GITHUB_ENV`:** `echo "BACKEND_PID=$!" >> "$GITHUB_ENV"` stores the process ID in case future steps need to signal or kill it. Not strictly required since the job ends naturally when all tests complete.

## Acceptance Criteria

- [ ] Opening a PR to `main` triggers the `E2E Tests` workflow within 30 seconds of the PR being created.
- [ ] Smoke tests pass in CI in under 8 minutes total (from workflow start to last test result).
- [ ] Playwright HTML report is uploaded as the `playwright-report` artifact and retained for 14 days.
- [ ] On test failure, `test-results/` (containing traces and screenshots) is uploaded and retained for 7 days.
- [ ] Merging to `main` triggers the `chromium` (full suite) project — insight tests run.
- [ ] No hardcoded secrets appear anywhere in the workflow YAML.
- [ ] The workflow does not modify `.github/workflows/deploy.yml`.

## Tests Required

Verify the workflow works end-to-end by:

1. Creating a test PR (even a documentation-only change) and confirming:
   - The `E2E Tests` workflow appears in the PR checks.
   - Only `chromium-smoke` project runs.
   - All smoke tests pass.
   - The `playwright-report` artifact appears in the workflow run summary.

2. Merging to `main` and confirming:
   - The `chromium` project runs (full suite including insights).
   - All tests pass.
   - Both `deploy.yml` and `e2e.yml` run in parallel (they are independent workflows).

3. Introducing a deliberate test failure (e.g., asserting wrong URL in `health.spec.ts`) and confirming:
   - The workflow fails.
   - The `test-results` artifact is uploaded with trace files.
   - The `playwright-report` artifact is still uploaded (due to `if: always()`).
