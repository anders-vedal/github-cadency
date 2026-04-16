import { test, expect } from '../../fixtures/auth'
import { InsightsPage } from '../../pages/InsightsPage'

test('admin sees workload insights page with sidebar', async ({ adminPage }) => {
  const insights = new InsightsPage(adminPage)
  await insights.gotoWorkload()
  await expect(adminPage).toHaveURL('/insights/workload')
  await insights.expectWorkloadLoaded()
})

test('non-admin is redirected away from /insights/workload', async ({ developerPage }) => {
  await developerPage.goto('/insights/workload')
  await expect(developerPage).toHaveURL(/\/team\/\d+/)
})
