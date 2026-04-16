import { test, expect } from '@playwright/test'
import { DashboardPage } from '../../pages/DashboardPage'

test('admin user sees dashboard at /', async ({ browser }) => {
  const context = await browser.newContext({
    storageState: 'playwright/.auth/admin.json',
  })
  const page = await context.newPage()
  const dashboard = new DashboardPage(page)
  await dashboard.goto()
  await expect(page).toHaveURL('/')
  await dashboard.expectLoaded()
  await context.close()
})

test('unauthenticated visit to / redirects to login', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
})
