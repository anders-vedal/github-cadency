import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useDevelopers } from '@/hooks/useDevelopers'
import { useRepos } from '@/hooks/useSync'
import type { AnalysisWizardType } from '@/utils/types'

interface StepConfigureScopeProps {
  analysisType: AnalysisWizardType
  scopeType: 'developer' | 'team' | 'repo' | null
  scopeId: string
  onScopeTypeChange: (scopeType: 'developer' | 'team' | 'repo') => void
  onScopeSelect: (scopeId: string, scopeName: string) => void
}

export default function StepConfigureScope({
  analysisType,
  scopeType,
  scopeId,
  onScopeTypeChange,
  onScopeSelect,
}: StepConfigureScopeProps) {
  const { data: developers = [] } = useDevelopers()
  const { data: repos = [] } = useRepos()

  const activeDevelopers = developers.filter((d) => d.is_active)
  const teams = [...new Set(activeDevelopers.map((d) => d.team).filter(Boolean))] as string[]

  const needsScopeTypeSelection = analysisType === 'sentiment'

  const renderScopeSelect = () => {
    if (scopeType === 'developer') {
      const selected = activeDevelopers.find((d) => String(d.id) === scopeId)
      return (
        <div className="space-y-2">
          <label className="text-sm font-medium">Select Developer</label>
          <Select
            value={scopeId || undefined}
            onValueChange={(v) => {
              if (!v) return
              const dev = activeDevelopers.find((d) => String(d.id) === v)
              onScopeSelect(v, dev ? `${dev.display_name} (@${dev.github_username})` : v)
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Choose a developer..." />
            </SelectTrigger>
            <SelectContent>
              {activeDevelopers.map((d) => (
                <SelectItem key={d.id} value={String(d.id)}>
                  {d.display_name} (@{d.github_username})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selected && (
            <div className="flex gap-2 text-xs text-muted-foreground">
              {selected.team && <Badge variant="outline">{selected.team}</Badge>}
              {selected.role && <Badge variant="outline">{selected.role}</Badge>}
            </div>
          )}
        </div>
      )
    }

    if (scopeType === 'team') {
      const showAll = analysisType === 'team_health'
      return (
        <div className="space-y-2">
          <label className="text-sm font-medium">Select Team</label>
          <Select
            value={scopeId || undefined}
            onValueChange={(v) => {
              if (!v) return
              onScopeSelect(v, v === '__all__' ? 'All teams' : v)
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Choose a team..." />
            </SelectTrigger>
            <SelectContent>
              {showAll && <SelectItem value="__all__">All teams</SelectItem>}
              {teams.map((t) => (
                <SelectItem key={t} value={t}>{t}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {scopeId && scopeId !== '__all__' && (
            <p className="text-xs text-muted-foreground">
              {activeDevelopers.filter((d) => d.team === scopeId).length} active members
            </p>
          )}
        </div>
      )
    }

    if (scopeType === 'repo') {
      return (
        <div className="space-y-2">
          <label className="text-sm font-medium">Select Repository</label>
          <Select
            value={scopeId || undefined}
            onValueChange={(v) => {
              if (!v) return
              const repo = repos.find((r) => String(r.id) === v)
              onScopeSelect(v, repo?.full_name ?? v)
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Choose a repository..." />
            </SelectTrigger>
            <SelectContent>
              {repos.filter((r) => r.is_tracked).map((r) => (
                <SelectItem key={r.id} value={String(r.id)}>
                  {r.full_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )
    }

    return null
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Configure Scope</h2>
        <p className="text-sm text-muted-foreground">
          {needsScopeTypeSelection
            ? 'Choose what scope to analyze, then select the specific target.'
            : `Select the ${scopeType} to analyze.`}
        </p>
      </div>

      {needsScopeTypeSelection && (
        <div className="grid gap-2 sm:grid-cols-3">
          {(['developer', 'team', 'repo'] as const).map((st) => (
            <Card
              key={st}
              className={cn(
                'cursor-pointer transition-all',
                scopeType === st ? 'ring-2 ring-primary' : 'hover:ring-1 hover:ring-primary/30',
              )}
              onClick={() => onScopeTypeChange(st)}
            >
              <CardContent className="flex items-center gap-3">
                <div
                  className={cn(
                    'h-3 w-3 shrink-0 rounded-full border-2',
                    scopeType === st ? 'border-primary bg-primary' : 'border-muted-foreground/30',
                  )}
                />
                <span className="text-sm font-medium capitalize">{st === 'repo' ? 'Repository' : st}</span>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {scopeType && renderScopeSelect()}
    </div>
  )
}
