import { test, expect } from '@playwright/test'
import { LoginPage } from '../../pages/LoginPage'

test('unauthenticated GET / redirects to /login', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
})

test('login page renders DevPulse heading and Login with GitHub button', async ({ page }) => {
  const loginPage = new LoginPage(page)
  await loginPage.goto()
  await loginPage.expectVisible()
})

test('authenticated user visiting /login is redirected to /', async ({ browser }) => {
  const context = await browser.newContext({
    storageState: 'playwright/.auth/admin.json',
  })
  const page = await context.newPage()
  await page.goto('/login')
  await expect(page).toHaveURL('/')
  await context.close()
})
