import { test, expect } from '@playwright/test'

test('GET /api/health returns 200 with status ok', async ({ request }) => {
  const response = await request.get('http://localhost:8000/api/health')
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(body).toEqual({ status: 'ok' })
})
