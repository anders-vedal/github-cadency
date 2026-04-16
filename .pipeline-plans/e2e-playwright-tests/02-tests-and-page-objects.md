---
Status: Planned
Priority: High
Type: Infrastructure
Apps: backend, frontend
Effort: Small
Linear: NOR-1125
---

# Sub-task 2: Tests and Page Objects

Write Playwright fixtures, page object models, smoke tests, and insight tests. This sub-task depends on sub-task 01 being merged first — the `e2e/` workspace, global-setup, and storageState files must already exist.

## What to Build

### 1. `e2e/fixtures/auth.ts` — Role-based page fixtures

```typescript
import { test as base, expect } from '@playwright/test'
import * as path from 'path'

type AuthFixtures = {
  adminPage: ReturnType<typeof base['extend']>['page']
  developerPage: ReturnType<typeof base['extend']>['page']
}

export const test = base.extend<AuthFixtures>({
  adminPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: path.join(__dirname, '..', 'playwright', '.auth', 'admin.json'),
    })
    const page = await context.newPage()
    await use(page)
    await context.close()
  },

  developerPage: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: path.join(__dirname, '..', 'playwright', '.auth', 'developer.json'),
    })
    const page = await context.newPage()
    await use(page)
    await context.close()
  },
})

export { expect }
```

### 2. `e2e/pages/LoginPage.ts`

```typescript
import type { Page } from '@playwright/test'

export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/login')
  }

  async expectVisible() {
    // "DevPulse" text — Login.tsx:29 uses shadcn CardTitle which renders as <div>, not <h1>
    await this.page.getByText('DevPulse').first().waitFor()
    // "Login with GitHub" button — Login.tsx:38
    await this.page.getByRole('button', { name: 'Login with GitHub' }).waitFor()
  }
}
```

### 3. `e2e/pages/DashboardPage.ts`

```typescript
import type { Page } from '@playwright/test'

export class DashboardPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/')
  }

  async expectLoaded() {
    // Top nav is always visible in Layout — frontend/src/components/Layout.tsx
    await this.page.getByRole('navigation').waitFor()
    // Dashboard renders stat cards — wait for the main content area to load
    // The page heading or any meaningful text confirms the lazy-loaded component rendered
    await this.page.getByText(/PRs|Merged|Cycle Time|Reviews/i).first().waitFor({ timeout: 10_000 })
  }
}
```

### 4. `e2e/pages/InsightsPage.ts`

```typescript
import type { Page } from '@playwright/test'

export class InsightsPage {
  constructor(private page: Page) {}

  async gotoWorkload() {
    await this.page.goto('/insights/workload')
  }

  async expectWorkloadLoaded() {
    // SidebarLayout wraps Insights — frontend/src/components/SidebarLayout.tsx
    // Sidebar contains "Insights" title and workload nav link
    await this.page.getByRole('navigation').waitFor()
    // WorkloadOverview page heading — frontend/src/pages/insights/WorkloadOverview.tsx
    await this.page.getByRole('heading', { name: /workload/i }).waitFor()
  }
}
```

### 5. `e2e/tests/smoke/health.spec.ts`

```typescript
import { test, expect } from '@playwright/test'

// Pure API test — no browser, no auth required
test('GET /api/health returns 200 with status ok', async ({ request }) => {
  const response = await request.get('http://localhost:8000/api/health')
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body).toEqual({ status: 'ok' })
})
```

Health endpoint is defined at `backend/app/main.py:586-588` — no authentication, returns `{"status": "ok"}`.

### 6. `e2e/tests/smoke/auth.spec.ts`

```typescript
import { test, expect } from '@playwright/test'
import { LoginPage } from '../../pages/LoginPage'

// All tests in this file use the default empty browser context (no storageState)

test('unauthenticated GET / redirects to /login', async ({ page }) => {
  await page.goto('/')
  // ProtectedRoute (App.tsx:102-116) uses <Navigate to="/login" replace />
  await expect(page).toHaveURL(/\/login/)
})

test('login page renders DevPulse heading and Login with GitHub button', async ({ page }) => {
  const loginPage = new LoginPage(page)
  await loginPage.goto()
  await loginPage.expectVisible()
})

test('authenticated user visiting /login is redirected to /', async ({ browser }) => {
  // Load admin storageState — simulates a logged-in admin
  // Path resolved relative to cwd (e2e/) when running `cd e2e && npx playwright test`
  const context = await browser.newContext({
    storageState: 'playwright/.auth/admin.json',
  })
  const page = await context.newPage()
  await page.goto('/login')
  // Login.tsx:12-14: if (!isLoading && user) return <Navigate to="/" replace />
  await expect(page).toHaveURL('/')
  await context.close()
})
```

### 7. `e2e/tests/smoke/dashboard.spec.ts`

```typescript
import { test, expect } from '@playwright/test'
import { DashboardPage } from '../../pages/DashboardPage'

// Uses chromium-smoke project — no storageState by default
// This test explicitly loads admin auth to verify dashboard renders

test('admin user sees dashboard at /', async ({ browser }) => {
  const context = await browser.newContext({
    storageState: 'playwright/.auth/admin.json',
  })
  const page = await context.newPage()
  const dashboard = new DashboardPage(page)
  await dashboard.goto()
  // App.tsx:150: admin lands at Dashboard, non-admin redirected to /team/:id
  await expect(page).toHaveURL('/')
  await dashboard.expectLoaded()
  await context.close()
})

test('unauthenticated visit to / redirects to login', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
})
```

### 8. `e2e/tests/insights/workload.spec.ts`

```typescript
import { test, expect } from '../../fixtures/auth'
import { InsightsPage } from '../../pages/InsightsPage'

test('admin sees workload insights page with sidebar', async ({ adminPage }) => {
  const insights = new InsightsPage(adminPage)
  await insights.gotoWorkload()
  // App.tsx:157-182: /insights/* renders SidebarLayout for admins
  await expect(adminPage).toHaveURL('/insights/workload')
  await insights.expectWorkloadLoaded()
})

test('non-admin is redirected away from /insights/workload', async ({ developerPage }) => {
  await developerPage.goto('/insights/workload')
  // App.tsx:181: non-admin gets <Navigate to="/" replace />
  // Non-admin admin lands at /team/:id (their own profile) — not /insights/*
  // Non-admin redirected: /insights/* → / → /team/:id
  await expect(developerPage).toHaveURL(/\/team\/\d+/)
})
```

## Implementation Notes

- **No `data-testid` attributes:** The codebase has no `data-testid` attributes. All selectors must use ARIA roles and text content — `getByRole`, `getByText`, `getByLabel`. This is already the Playwright recommended approach and works with shadcn/ui components which render semantic HTML.
- **`chromium-smoke` project has no `storageState` in config:** Tests in `smoke/` that need auth must create their own `browser.newContext({ storageState: '...' })` inline. Tests that test unauthenticated flows use the default `page` fixture (empty context).
- **`chromium` project uses `admin.json` storageState by default:** Tests under `tests/insights/` that use the `adminPage` fixture from `e2e/fixtures/auth.ts` inherit a context already seeded with the admin JWT. Tests that need the developer role use `developerPage`.
- **`storageState` path resolution:** In `playwright.config.ts` project definitions, paths are relative to the config file dir (`e2e/`). In `browser.newContext()` inside test files, paths are relative to the cwd (`e2e/` when running `cd e2e && npx playwright test`). In fixture files (`e2e/fixtures/auth.ts`), use `path.join(__dirname, '..', 'playwright', '.auth', 'admin.json')` for portability. In inline test code, use `'playwright/.auth/admin.json'` (relative to cwd).
- **`ProtectedRoute` auth flow** (`frontend/src/App.tsx:102-117`): Reads `localStorage.getItem('devpulse_token')`. If missing, redirects to `/login`. If present but user fails to load from API, removes token and redirects. The seeded JWT must be valid against the running backend.
- **Admin redirect:** `App.tsx:150` — `auth.isAdmin ? <Dashboard /> : <Navigate to={/team/${auth.user?.developer_id}} replace />`. The non-admin `e2e-dev` developer will be redirected to `/team/<id>` where `<id>` is the database row ID assigned during seeding (unknown ahead of time, hence `not.toHaveURL(/\/insights\//)` assertion).
- **Non-admin blocked from `/insights/*`:** `App.tsx:181` — `auth.isAdmin ? <SidebarLayout> : <Navigate to="/" replace />`. For a non-admin, navigating to `/insights/workload` redirects to `/`, which then redirects to `/team/:id`.
- **Workload page heading:** `frontend/src/pages/insights/WorkloadOverview.tsx` renders a heading. Use `getByRole('heading', { name: /workload/i })` with case-insensitive match to be resilient to exact casing.
- **`InsightsPage.expectWorkloadLoaded()`:** The sidebar is rendered by `SidebarLayout` (`frontend/src/components/SidebarLayout.tsx`) and contains nav links. Waiting for `getByRole('navigation')` confirms the layout rendered. Then wait for the heading to confirm the route component loaded.
- **Test isolation:** Each test must be fully independent. No shared mutable state between tests. The `adminPage` and `developerPage` fixtures create a fresh browser context per test.
- **`request` fixture for API tests:** Playwright's built-in `request` fixture sends HTTP requests from Node, not the browser. Use `http://localhost:8000` directly (not the Vite proxy) for API tests.

## Acceptance Criteria

- [ ] `cd e2e && npx playwright test --project=chromium-smoke` passes all 5 smoke tests (health, auth x3, dashboard x2) with no failures.
- [ ] `cd e2e && npx playwright test --project=chromium` passes the 2 workload insight tests.
- [ ] `cd e2e && npx playwright test` (all projects) passes in under 60 seconds against a warm local stack.
- [ ] Each test is independent — running tests in any order produces the same result.
- [ ] No test writes to the database or leaves side effects.
- [ ] `npx playwright show-report` opens a valid HTML report with all test results.

## Tests Required

These files are the tests themselves. Manual verification steps for the developer implementing this sub-task:

1. Start E2E stack: `docker compose -f docker-compose.e2e.yml up -d`
2. Run migrations: `cd backend && DATABASE_URL=postgresql+asyncpg://devpulse:devpulse@localhost:5434/devpulse_e2e alembic upgrade head`
3. Run seed: `cd backend && DATABASE_URL=... JWT_SECRET=... python -m scripts.e2e_seed`
4. Run smoke: `cd e2e && npx playwright test --project=chromium-smoke`
5. Run full suite: `cd e2e && npx playwright test`
6. Verify report: `cd e2e && npx playwright show-report`
