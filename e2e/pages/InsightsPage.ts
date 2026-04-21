import type { Page } from '@playwright/test'

export class InsightsPage {
  constructor(private page: Page) {}

  async gotoWorkload() {
    await this.page.goto('/insights/workload')
  }

  async expectWorkloadLoaded() {
    await this.page.getByRole('navigation').waitFor()
    await this.page.getByRole('heading', { level: 1, name: /workload/i }).waitFor()
  }
}
