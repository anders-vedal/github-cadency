import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'
import type {
  ChattyIssueRow,
  ConversationsScatterPoint,
  FirstResponseHistogramBucket,
  ParticipantDistributionBucket,
} from '@/utils/types'

export interface ChattiestIssuesFilters {
  dateFrom?: string
  dateTo?: string
  limit?: number
  projectId?: number
  creatorId?: number
  assigneeId?: number
  label?: string
  priority?: number
  hasLinkedPr?: boolean
}

export function useChattiestIssues(filters: ChattiestIssuesFilters = {}) {
  const params = new URLSearchParams()
  if (filters.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters.dateTo) params.set('date_to', filters.dateTo)
  if (filters.limit != null) params.set('limit', String(filters.limit))
  if (filters.projectId != null) params.set('project_id', String(filters.projectId))
  if (filters.creatorId != null) params.set('creator_id', String(filters.creatorId))
  if (filters.assigneeId != null) params.set('assignee_id', String(filters.assigneeId))
  if (filters.label) params.set('label', filters.label)
  if (filters.priority != null) params.set('priority', String(filters.priority))
  if (filters.hasLinkedPr != null) params.set('has_linked_pr', String(filters.hasLinkedPr))
  return useQuery<ChattyIssueRow[]>({
    queryKey: ['chattiest-issues', filters],
    queryFn: () => apiFetch(`/conversations/chattiest?${params}`),
    staleTime: 60_000,
  })
}

export function useCommentBounceScatter(dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<ConversationsScatterPoint[]>({
    queryKey: ['conversations-scatter', dateFrom, dateTo],
    queryFn: () => apiFetch(`/conversations/scatter?${params}`),
    staleTime: 60_000,
  })
}

export function useFirstResponseHistogram(dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<FirstResponseHistogramBucket[]>({
    queryKey: ['first-response-histogram', dateFrom, dateTo],
    queryFn: () => apiFetch(`/conversations/first-response?${params}`),
    staleTime: 60_000,
  })
}

export function useParticipantDistribution(dateFrom?: string, dateTo?: string) {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  return useQuery<ParticipantDistributionBucket[]>({
    queryKey: ['participant-distribution', dateFrom, dateTo],
    queryFn: () => apiFetch(`/conversations/participants?${params}`),
    staleTime: 60_000,
  })
}

export interface LinearLabelRow {
  name: string
  count: number
}

export function useLinearLabels(enabled = true) {
  return useQuery<{ labels: LinearLabelRow[] }>({
    queryKey: ['linear-labels'],
    queryFn: () => apiFetch('/linear/labels'),
    staleTime: 5 * 60_000, // labels change rarely
    enabled,
  })
}
