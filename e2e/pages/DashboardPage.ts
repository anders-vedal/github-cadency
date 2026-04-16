import type { Page } from '@playwright/test'

export class DashboardPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/')
  }

  async expectLoaded() {
    await this.page.getByRole('navigation').waitFor()
    await this.page.getByText(/PRs|Merged|Cycle Time|Reviews/i).first().waitFor({ timeout: 10_000 })
  }
}
