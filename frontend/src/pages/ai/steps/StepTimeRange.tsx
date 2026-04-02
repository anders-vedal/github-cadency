import { useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useRepos } from '@/hooks/useSync'
import type { TimeRangeOption } from '@/utils/types'

interface StepTimeRangeProps {
  timeRange: TimeRangeOption
  customDate: string
  repoIds: number[]
  onTimeRangeChange: (range: TimeRangeOption) => void
  onCustomDateChange: (date: string) => void
  onRepoIdsChange: (ids: number[]) => void
}

const options: { value: TimeRangeOption; label: string; description: string }[] = [
  { value: 'last_7d', label: 'Last 7 days', description: 'Analyze the past week' },
  { value: 'last_14d', label: 'Last 14 days', description: 'Analyze the past two weeks' },
  { value: 'last_30d', label: 'Last 30 days', description: 'Analyze the past month (default)' },
  { value: 'last_60d', label: 'Last 60 days', description: 'Analyze the past two months' },
  { value: 'last_90d', label: 'Last 90 days', description: 'Analyze the past quarter' },
  { value: 'custom', label: 'Custom date', description: 'Choose a specific start date' },
]

export default function StepTimeRange({
  timeRange,
  customDate,
  repoIds,
  onTimeRangeChange,
  onCustomDateChange,
  onRepoIdsChange,
}: StepTimeRangeProps) {
  const { data: repos = [] } = useRepos()
  const trackedRepos = repos.filter((r) => r.is_tracked)
  const [repoFilterOpen, setRepoFilterOpen] = useState(repoIds.length > 0)
  const [repoSearch, setRepoSearch] = useState('')

  const filteredRepos = trackedRepos.filter((r) =>
    (r.full_name ?? '').toLowerCase().includes(repoSearch.toLowerCase()),
  )

  const toggleRepo = (id: number) => {
    onRepoIdsChange(
      repoIds.includes(id) ? repoIds.filter((x) => x !== id) : [...repoIds, id],
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Time Range</h2>
        <p className="text-sm text-muted-foreground">How far back should the analysis look?</p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((opt) => (
          <Card
            key={opt.value}
            className={cn(
              'cursor-pointer transition-all',
              timeRange === opt.value ? 'ring-2 ring-primary' : 'hover:ring-1 hover:ring-primary/30',
            )}
            onClick={() => onTimeRangeChange(opt.value)}
          >
            <CardContent className="flex items-center gap-3">
              <div
                className={cn(
                  'h-3 w-3 shrink-0 rounded-full border-2',
                  timeRange === opt.value ? 'border-primary bg-primary' : 'border-muted-foreground/30',
                )}
              />
              <div>
                <div className="text-sm font-medium">{opt.label}</div>
                <div className="text-xs text-muted-foreground">{opt.description}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {timeRange === 'custom' && (
        <div className="flex items-center gap-3">
          <Label htmlFor="ai-custom-date">Start date:</Label>
          <Input
            id="ai-custom-date"
            type="date"
            value={customDate}
            onChange={(e) => onCustomDateChange(e.target.value)}
            className="w-44"
          />
        </div>
      )}

      {/* Repo filter — collapsible advanced section */}
      <div className="rounded-md border p-3">
        <button
          type="button"
          className="flex w-full items-center gap-2 text-sm font-medium"
          onClick={() => setRepoFilterOpen(!repoFilterOpen)}
        >
          {repoFilterOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          Filter by specific repositories (optional)
          {repoIds.length > 0 && (
            <Badge variant="secondary" className="ml-auto text-xs">
              {repoIds.length} selected
            </Badge>
          )}
          {repoIds.length === 0 && (
            <span className="ml-auto text-xs text-muted-foreground">All repositories</span>
          )}
        </button>

        {repoFilterOpen && (
          <div className="mt-3 space-y-2">
            <Input
              placeholder="Search repos..."
              value={repoSearch}
              onChange={(e) => setRepoSearch(e.target.value)}
              className="h-8 text-sm"
            />
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => onRepoIdsChange(trackedRepos.map((r) => r.id))}
              >
                Select All
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => onRepoIdsChange([])}
              >
                Deselect All
              </Button>
            </div>
            <div className="max-h-48 overflow-y-auto space-y-1">
              {filteredRepos.map((repo) => (
                <label
                  key={repo.id}
                  className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted/50 cursor-pointer"
                >
                  <Checkbox
                    checked={repoIds.includes(repo.id)}
                    onCheckedChange={() => toggleRepo(repo.id)}
                  />
                  <span>{repo.full_name}</span>
                  {repo.language && (
                    <Badge variant="outline" className="ml-auto text-xs">{repo.language}</Badge>
                  )}
                </label>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
