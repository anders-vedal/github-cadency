import { Fragment, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useCollaboration } from '@/hooks/useStats'
import { useDevelopers } from '@/hooks/useDevelopers'
import ErrorCard from '@/components/ErrorCard'
import PairDetailSheet from '@/components/PairDetailSheet'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { CollaborationPair, CollaborationInsights } from '@/utils/types'

export default function CollaborationMatrix() {
  const { dateFrom, dateTo } = useDateRange()
  const [teamFilter, setTeamFilter] = useState<string>('')
  const [selectedPair, setSelectedPair] = useState<{ reviewerId: number; authorId: number } | null>(null)

  const { data, isLoading, isError, refetch } = useCollaboration(teamFilter || undefined, dateFrom, dateTo)
  const { data: developers } = useDevelopers()

  const teams = useMemo(() => {
    if (!developers) return []
    const set = new Set(developers.map((d) => d.team).filter(Boolean) as string[])
    return Array.from(set).sort()
  }, [developers])

  if (isError) {
    return <ErrorCard message="Could not load collaboration data." onRetry={refetch} />
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Collaboration Matrix</h1>
        <Skeleton className="h-64 w-full rounded-lg" />
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32 rounded-lg" />)}
        </div>
      </div>
    )
  }

  if (!data || data.matrix.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Collaboration Matrix</h1>
        <p className="text-muted-foreground">No review data available for this period.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Collaboration Matrix</h1>
        {teams.length > 0 && (
          <select
            value={teamFilter}
            onChange={(e) => setTeamFilter(e.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            <option value="">All teams</option>
            {teams.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}
      </div>

      <HeatmapGrid matrix={data.matrix} onCellClick={(reviewerId, authorId) => setSelectedPair({ reviewerId, authorId })} />
      <InsightsPanel insights={data.insights} />

      <PairDetailSheet
        reviewerId={selectedPair?.reviewerId ?? null}
        authorId={selectedPair?.authorId ?? null}
        open={selectedPair !== null}
        onOpenChange={(open) => { if (!open) setSelectedPair(null) }}
      />
    </div>
  )
}

// --- Heatmap Grid ---

function HeatmapGrid({ matrix, onCellClick }: { matrix: CollaborationPair[]; onCellClick: (reviewerId: number, authorId: number) => void }) {
  const [hoveredCell, setHoveredCell] = useState<{ reviewer: string; author: string } | null>(null)

  // Build unique reviewer and author lists
  const { reviewers, authors, cellMap, maxCount } = useMemo(() => {
    const reviewerSet = new Map<number, string>()
    const authorSet = new Map<number, string>()
    const map = new Map<string, CollaborationPair>()
    let max = 0

    for (const pair of matrix) {
      reviewerSet.set(pair.reviewer_id, pair.reviewer_name)
      authorSet.set(pair.author_id, pair.author_name)
      map.set(`${pair.reviewer_id}-${pair.author_id}`, pair)
      if (pair.reviews_count > max) max = pair.reviews_count
    }

    return {
      reviewers: Array.from(reviewerSet.entries()).map(([id, name]) => ({ id, name })),
      authors: Array.from(authorSet.entries()).map(([id, name]) => ({ id, name })),
      cellMap: map,
      maxCount: max,
    }
  }, [matrix])

  if (reviewers.length === 0 || authors.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Review Heatmap</CardTitle>
        <p className="text-xs text-muted-foreground">Rows = reviewers, Columns = PR authors. Color intensity = review count.</p>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <div
            className="inline-grid gap-px"
            style={{
              gridTemplateColumns: `120px repeat(${authors.length}, minmax(48px, 64px))`,
            }}
          >
            {/* Header row */}
            <div />
            {authors.map((a) => (
              <div
                key={`h-${a.id}`}
                className="truncate px-1 py-1 text-center text-[11px] font-medium text-muted-foreground"
                title={a.name}
              >
                {a.name.split(' ')[0]}
              </div>
            ))}

            {/* Data rows */}
            {reviewers.map((r) => (
              <Fragment key={`r-${r.id}`}>
                <div
                  className="truncate pr-2 py-1 text-right text-[11px] font-medium text-muted-foreground"
                  title={r.name}
                >
                  {r.name}
                </div>
                {authors.map((a) => {
                  const pair = cellMap.get(`${r.id}-${a.id}`)
                  const count = pair?.reviews_count ?? 0
                  const intensity = maxCount > 0 ? count / maxCount : 0
                  const isSelf = r.id === a.id
                  const isHovered = hoveredCell?.reviewer === r.name && hoveredCell?.author === a.name

                  const isClickable = !isSelf && count > 0

                  return (
                    <div
                      key={`c-${r.id}-${a.id}`}
                      className={cn(
                        'relative flex items-center justify-center rounded-sm text-[10px] font-medium transition-all',
                        isSelf ? 'bg-muted/50 cursor-default' : count > 0 ? 'cursor-pointer hover:ring-2 hover:ring-primary/50' : 'cursor-default hover:ring-1 hover:ring-foreground/20',
                        isHovered && 'ring-2 ring-primary'
                      )}
                      onClick={isClickable ? () => onCellClick(r.id, a.id) : undefined}
                      style={{
                        backgroundColor: isSelf
                          ? undefined
                          : count > 0
                            ? `hsl(var(--primary) / ${0.1 + intensity * 0.7})`
                            : undefined,
                        minHeight: '32px',
                      }}
                      onMouseEnter={() => setHoveredCell({ reviewer: r.name, author: a.name })}
                      onMouseLeave={() => setHoveredCell(null)}
                      title={
                        isSelf
                          ? 'Self'
                          : pair
                            ? `${r.name} → ${a.name}: ${count} reviews (${pair.approvals} approved, ${pair.changes_requested} changes requested)`
                            : `${r.name} → ${a.name}: 0 reviews`
                      }
                    >
                      {isSelf ? (
                        <span className="text-muted-foreground/40">—</span>
                      ) : count > 0 ? (
                        <span className={cn(
                          intensity > 0.5 ? 'text-primary-foreground' : 'text-foreground'
                        )}>
                          {count}
                        </span>
                      ) : null}
                    </div>
                  )
                })}
              </Fragment>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// --- Insights Panel ---

function InsightsPanel({ insights }: { insights: CollaborationInsights }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {/* Bus Factors */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Bus Factors</CardTitle>
          <p className="text-xs text-muted-foreground">Repos where one reviewer handles {'>'}70% of reviews</p>
        </CardHeader>
        <CardContent>
          {insights.bus_factors.length === 0 ? (
            <p className="text-sm text-muted-foreground">No bus factors detected.</p>
          ) : (
            <ul className="space-y-2">
              {insights.bus_factors.map((bf) => (
                <li key={`${bf.repo_name}-${bf.sole_reviewer_id}`} className="flex items-center justify-between text-sm">
                  <span>
                    <span className="font-medium">{bf.sole_reviewer_name}</span>
                    <span className="text-muted-foreground"> in {bf.repo_name}</span>
                  </span>
                  <Badge variant="secondary" className="bg-red-500/10 text-red-600">
                    {bf.review_share_pct.toFixed(0)}%
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Silos */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Team Silos</CardTitle>
          <p className="text-xs text-muted-foreground">Team pairs with zero cross-team reviews</p>
        </CardHeader>
        <CardContent>
          {insights.silos.length === 0 ? (
            <p className="text-sm text-emerald-600">No silos detected — all teams collaborate.</p>
          ) : (
            <ul className="space-y-2">
              {insights.silos.map((silo, i) => (
                <li key={i} className="text-sm">
                  <span className="font-medium">{silo.team_a}</span>
                  <span className="text-muted-foreground"> ↔ </span>
                  <span className="font-medium">{silo.team_b}</span>
                  {silo.note && (
                    <span className="ml-1 text-xs text-muted-foreground">— {silo.note}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Isolated Developers */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Isolated Developers</CardTitle>
          <p className="text-xs text-muted-foreground">Developers with minimal review interaction</p>
        </CardHeader>
        <CardContent>
          {insights.isolated_developers.length === 0 ? (
            <p className="text-sm text-emerald-600">No isolated developers.</p>
          ) : (
            <ul className="space-y-1">
              {insights.isolated_developers.map((dev) => (
                <li key={dev.developer_id} className="text-sm">
                  <Link to={`/team/${dev.developer_id}`} className="text-primary hover:underline">
                    {dev.display_name}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Strongest Pairs */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Strongest Pairs</CardTitle>
          <p className="text-xs text-muted-foreground">Most active reviewer-author pairs</p>
        </CardHeader>
        <CardContent>
          {insights.strongest_pairs.length === 0 ? (
            <p className="text-sm text-muted-foreground">Not enough data.</p>
          ) : (
            <ul className="space-y-2">
              {insights.strongest_pairs.map((pair) => {
                // Check reciprocity: is there a reverse pair in strongest_pairs?
                const reverse = insights.strongest_pairs.find(
                  (p) => p.reviewer_id === pair.author_id && p.author_id === pair.reviewer_id
                )
                return (
                  <li key={`${pair.reviewer_id}-${pair.author_id}`} className="flex items-center justify-between text-sm">
                    <span>
                      <span className="font-medium">{pair.reviewer_name}</span>
                      <span className="text-muted-foreground">
                        {reverse ? ' ↔ ' : ' → '}
                      </span>
                      <span className="font-medium">{pair.author_name}</span>
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">{pair.reviews_count} reviews</span>
                      {reverse ? (
                        <Badge variant="secondary" className="bg-emerald-500/10 text-emerald-600 text-[10px]">
                          mutual
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="bg-amber-500/10 text-amber-600 text-[10px]">
                          one-way
                        </Badge>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
