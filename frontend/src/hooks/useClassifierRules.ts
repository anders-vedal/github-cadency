import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { apiFetch } from '@/utils/api'

export interface ClassifierRule {
  id: number
  kind: 'incident' | 'ai_reviewer' | 'ai_author'
  rule_type: string
  pattern: string
  is_hotfix: boolean
  is_incident: boolean
  priority: number
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface ClassifierRulesResponse {
  rules: ClassifierRule[]
}

export interface ClassifierRuleCreate {
  kind: ClassifierRule['kind']
  rule_type: string
  pattern: string
  is_hotfix?: boolean
  is_incident?: boolean
  priority?: number
  enabled?: boolean
}

export function useClassifierRules(kind?: ClassifierRule['kind']) {
  return useQuery<ClassifierRulesResponse>({
    queryKey: ['classifier-rules', kind ?? 'all'],
    queryFn: () =>
      apiFetch(
        kind
          ? `/admin/classifier-rules?kind=${kind}`
          : '/admin/classifier-rules',
      ),
    staleTime: 30_000,
  })
}

export function useCreateClassifierRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ClassifierRuleCreate) =>
      apiFetch<ClassifierRule>('/admin/classifier-rules', {
        method: 'POST',
        body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json' },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['classifier-rules'] })
      toast.success('Rule added')
    },
    onError: (err: Error) => toast.error(err.message || 'Failed to add rule'),
  })
}

export function useDeleteClassifierRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ruleId: number) =>
      apiFetch(`/admin/classifier-rules/${ruleId}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['classifier-rules'] })
      toast.success('Rule deleted')
    },
    onError: () => toast.error('Failed to delete rule'),
  })
}

export function useToggleClassifierRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      apiFetch<ClassifierRule>(`/admin/classifier-rules/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
        headers: { 'Content-Type': 'application/json' },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['classifier-rules'] })
    },
    onError: () => toast.error('Failed to update rule'),
  })
}
