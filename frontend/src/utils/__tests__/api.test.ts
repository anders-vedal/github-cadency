import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiFetch } from '../api'

describe('apiFetch', () => {
  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('prepends /api to the path', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ data: 'test' }),
    })

    await apiFetch('/developers')
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/developers',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      }),
    )
  })

  it('includes Authorization header when token exists', async () => {
    localStorage.setItem('devpulse_token', 'my-token')
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    })

    await apiFetch('/developers')
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/developers',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer my-token',
        }),
      }),
    )
  })

  it('omits Authorization header when no token', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    })

    await apiFetch('/developers')
    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers).not.toHaveProperty('Authorization')
  })

  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      text: () => Promise.resolve('Not found'),
    })

    await expect(apiFetch('/developers/999')).rejects.toThrow('404: Not found')
  })

  it('returns parsed JSON on success', async () => {
    const mockData = [{ id: 1, name: 'Dev' }]
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockData),
    })

    const result = await apiFetch('/developers')
    expect(result).toEqual(mockData)
  })

  it('passes through custom options', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    })

    await apiFetch('/developers', {
      method: 'POST',
      body: JSON.stringify({ name: 'test' }),
    })

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/developers',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'test' }),
      }),
    )
  })
})
