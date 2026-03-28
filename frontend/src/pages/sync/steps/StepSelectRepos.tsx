import { useState, useMemo } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import type { Repo } from '@/utils/types'

interface StepSelectReposProps {
  repos: Repo[]
  selectedIds: number[]
  onChangeSelection: (ids: number[]) => void
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never synced'
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function StepSelectRepos({
  repos,
  selectedIds,
  onChangeSelection,
}: StepSelectReposProps) {
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search) return repos
    const lower = search.toLowerCase()
    return repos.filter(
      (r) => r.full_name?.toLowerCase().includes(lower) || r.name?.toLowerCase().includes(lower)
    )
  }, [repos, search])

  const trackedIds = useMemo(() => repos.filter((r) => r.is_tracked).map((r) => r.id), [repos])

  const toggleRepo = (id: number) => {
    if (selectedIds.includes(id)) {
      onChangeSelection(selectedIds.filter((rid) => rid !== id))
    } else {
      onChangeSelection([...selectedIds, id])
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Input
          placeholder="Search repos..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChangeSelection(trackedIds)}
        >
          Select All Tracked
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChangeSelection([])}
        >
          Deselect All
        </Button>
        <span className="ml-auto text-sm text-muted-foreground">
          {selectedIds.length} selected
        </span>
      </div>

      <div className="max-h-80 space-y-1 overflow-y-auto rounded-md border p-2">
        {filtered.map((repo) => {
          const isSelected = selectedIds.includes(repo.id)
          return (
            <label
              key={repo.id}
              className={`flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-muted/50 ${
                !repo.is_tracked ? 'opacity-50' : ''
              }`}
            >
              <Checkbox
                checked={isSelected}
                onCheckedChange={() => toggleRepo(repo.id)}
              />
              <span className="flex-1 font-medium">{repo.full_name}</span>
              {repo.language && (
                <Badge variant="outline" className="text-xs">
                  {repo.language}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">
                {repo.pr_count} PRs, {repo.issue_count} issues
              </span>
              <span className="w-24 text-right text-xs text-muted-foreground">
                {timeAgo(repo.last_synced_at)}
              </span>
            </label>
          )
        })}
        {filtered.length === 0 && (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No repos match your search.
          </p>
        )}
      </div>
    </div>
  )
}
