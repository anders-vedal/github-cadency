import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useDevelopers, useDeveloper, useCreateDeveloper } from '../useDevelopers'

// Mock apiFetch
vi.mock('@/utils/api', () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from '@/utils/api'
const mockApiFetch = vi.mocked(apiFetch)

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

describe('useDevelopers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches developers list', async () => {
    const mockDevs = [
      { id: 1, github_username: 'dev1', display_name: 'Developer 1' },
    ]
    mockApiFetch.mockResolvedValueOnce(mockDevs)

    const { result } = renderHook(() => useDevelopers(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockDevs)
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('/developers'),
    )
  })

  it('passes team filter parameter', async () => {
    mockApiFetch.mockResolvedValueOnce([])

    const { result } = renderHook(() => useDevelopers('backend'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('team=backend'),
    )
  })

  it('handles error', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('500: Server error'))

    const { result } = renderHook(() => useDevelopers(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error?.message).toBe('500: Server error')
  })
})

describe('useDeveloper', () => {
  it('fetches single developer by id', async () => {
    const mockDev = { id: 1, github_username: 'dev1', display_name: 'Dev 1' }
    mockApiFetch.mockResolvedValueOnce(mockDev)

    const { result } = renderHook(() => useDeveloper(1), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(mockDev)
    expect(mockApiFetch).toHaveBeenCalledWith('/developers/1')
  })
})

describe('useCreateDeveloper', () => {
  it('calls POST and returns created developer', async () => {
    const newDev = {
      id: 2,
      github_username: 'newdev',
      display_name: 'New Dev',
    }
    mockApiFetch.mockResolvedValueOnce(newDev)

    const { result } = renderHook(() => useCreateDeveloper(), {
      wrapper: createWrapper(),
    })

    result.current.mutate({
      github_username: 'newdev',
      display_name: 'New Dev',
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(newDev)
    expect(mockApiFetch).toHaveBeenCalledWith('/developers', {
      method: 'POST',
      body: JSON.stringify({
        github_username: 'newdev',
        display_name: 'New Dev',
      }),
    })
  })
})
