import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type { Developer, DeveloperCreate, DeveloperUpdate } from '@/utils/types'

export function useDevelopers(team?: string, isActive = true) {
  const params = new URLSearchParams()
  if (team) params.set('team', team)
  params.set('is_active', String(isActive))
  return useQuery<Developer[]>({
    queryKey: ['developers', team, isActive],
    queryFn: () => apiFetch(`/developers?${params}`),
  })
}

export function useDeveloper(id: number) {
  return useQuery<Developer>({
    queryKey: ['developer', id],
    queryFn: () => apiFetch(`/developers/${id}`),
    enabled: !!id,
  })
}

export function useCreateDeveloper() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: DeveloperCreate) =>
      apiFetch<Developer>('/developers', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['developers'] }),
  })
}

export function useUpdateDeveloper(id: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: DeveloperUpdate) =>
      apiFetch<Developer>(`/developers/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['developers'] })
      qc.invalidateQueries({ queryKey: ['developer', id] })
    },
  })
}

export function useDeleteDeveloper() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/developers/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['developers'] }),
  })
}
