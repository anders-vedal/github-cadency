import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/utils/api'

export interface MetricSpec {
  key: string
  label: string
  category: string
  is_activity: boolean
  paired_outcome_key: string | null
  visibility_default: 'self' | 'team' | 'admin'
  is_distribution: boolean
  goodhart_risk: 'low' | 'medium' | 'high'
  goodhart_notes: string
  description: string
}

export interface BannedMetric {
  key: string
  reason: string
}

export interface MetricsCatalog {
  metrics: MetricSpec[]
  banned: BannedMetric[]
}

export function useMetricsCatalog() {
  return useQuery<MetricsCatalog>({
    queryKey: ['metrics-catalog'],
    queryFn: () => apiFetch('/metrics/catalog'),
    // Catalog is essentially static per deploy — don't refetch aggressively
    staleTime: 15 * 60_000,
  })
}
