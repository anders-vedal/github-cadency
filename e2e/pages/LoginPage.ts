import type { Page } from '@playwright/test'

export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/login')
  }

  async expectVisible() {
    await this.page.getByText('DevPulse').first().waitFor()
    await this.page.getByRole('button', { name: 'Login with GitHub' }).waitFor()
  }
}
