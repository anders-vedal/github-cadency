import type { WorkCategory } from '@/utils/types'

export const CATEGORY_CONFIG: Record<WorkCategory, { label: string; color: string }> = {
  feature: { label: 'Feature', color: '#3b82f6' },
  bugfix: { label: 'Bug Fix', color: '#ef4444' },
  tech_debt: { label: 'Tech Debt', color: '#f59e0b' },
  ops: { label: 'Ops', color: '#22c55e' },
  unknown: { label: 'Unknown', color: '#94a3b8' },
}

export const CATEGORY_ORDER: WorkCategory[] = ['feature', 'bugfix', 'tech_debt', 'ops', 'unknown']
