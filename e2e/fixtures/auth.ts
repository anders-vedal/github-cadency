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
