import { useParams, Link } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useCollaborationPairDetail } from '@/hooks/useStats'
import ErrorCard from '@/components/ErrorCard'
import {
  RelationshipBadge,
  CommentTypeBar,
  QUALITY_TIER_COLORS,
  COMMENT_TYPE_COLORS,
} from '@/components/PairDetailSheet'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { ArrowLeft, ArrowRight, ExternalLink } from 'lucide-react'
import { useState, useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { CollaborationPairDetail } from '@/utils/types'

export default function CollaborationPairPage() {
  const { reviewerId, authorId } = useParams<{ reviewerId: string; authorId: string }>()
  const { dateFrom, dateTo } = useDateRange()
  const rId = reviewerId ? Number(reviewerId) : null
  const aId = authorId ? Number(authorId) : null

  const { data, isLoading, isError, refetch } = useCollaborationPairDetail(rId, aId, dateFrom, dateTo)

  if (isError) return <ErrorCard message="Could not load pair detail." onRetry={refetch} />

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-lg" />)}
        </div>
        <Skeleton className="h-48 w-full rounded-lg" />
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="space-y-6">
      <Header data={data} />
      <StatsCards data={data} />
      <RelationshipCard data={data} />
      <div className="grid gap-4 lg:grid-cols-2">
        <CommentTypeChart data={data} />
        <QualityTierChart data={data} />
      </div>
      <RecentPRsTable data={data} />
    </div>
  )
}

function Header({ data }: { data: CollaborationPairDetail }) {
  return (
    <div className="space-y-1">
      <Link to="/insights/collaboration" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3 w-3" /> Back to Collaboration Matrix
      </Link>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          {data.reviewer_avatar_url && <img src={data.reviewer_avatar_url} alt="" className="h-8 w-8 rounded-full" />}
          <div>
            <Link to={`/team/${data.reviewer_id}`} className="text-sm font-semibold hover:underline">{data.reviewer_name}</Link>
            {data.reviewer_team && <p className="text-[10px] text-muted-foreground">{data.reviewer_team}</p>}
          </div>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
        <div className="flex items-center gap-2">
          {data.author_avatar_url && <img src={data.author_avatar_url} alt="" className="h-8 w-8 rounded-full" />}
          <div>
            <Link to={`/team/${data.author_id}`} className="text-sm font-semibold hover:underline">{data.author_name}</Link>
            {data.author_team && <p className="text-[10px] text-muted-foreground">{data.author_team}</p>}
          </div>
        </div>
      </div>
    </div>
  )
}

function StatsCards({ data }: { data: CollaborationPairDetail }) {
  return (
    <div className="grid gap-4 sm:grid-cols-4">
      <Card>
        <CardContent className="pt-4">
          <p className="text-xs text-muted-foreground">Total Reviews</p>
          <p className="text-2xl font-bold">{data.total_reviews}</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <p className="text-xs text-muted-foreground">Approval Rate</p>
          <p className="text-2xl font-bold">{Math.round(data.approval_rate * 100)}%</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <p className="text-xs text-muted-foreground">Avg Quality</p>
          <Badge variant="secondary" className={cn('mt-1 text-xs', QUALITY_TIER_COLORS[data.avg_quality_tier] ?? '')}>
            {data.avg_quality_tier}
          </Badge>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-4">
          <p className="text-xs text-muted-foreground">Total Comments</p>
          <p className="text-2xl font-bold">{data.total_comments}</p>
        </CardContent>
      </Card>
    </div>
  )
}

function RelationshipCard({ data }: { data: CollaborationPairDetail }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">Relationship Classification</CardTitle>
      </CardHeader>
      <CardContent>
        <RelationshipBadge relationship={data.relationship} />
      </CardContent>
    </Card>
  )
}

function CommentTypeChart({ data }: { data: CollaborationPairDetail }) {
  const chartId = useId()
  const chartData = data.comment_type_breakdown.map((item) => ({
    name: item.comment_type,
    value: item.count,
    fill: COMMENT_TYPE_COLORS[item.comment_type] ?? 'hsl(var(--muted-foreground))',
  }))

  if (chartData.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Comment Types</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No comments in this period.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">Comment Types</CardTitle>
      </CardHeader>
      <CardContent>
        <CommentTypeBar breakdown={data.comment_type_breakdown} total={data.total_comments} />
        <div className="mt-3 h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ left: 80, right: 20, top: 5, bottom: 5 }}>
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={75} />
              <Tooltip />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {chartData.map((entry, idx) => {
                  // Map Tailwind class names to CSS-friendly colors for Recharts
                  const colorMap: Record<string, string> = {
                    'bg-red-500': 'hsl(0, 84%, 60%)',
                    'bg-purple-500': 'hsl(271, 91%, 65%)',
                    'bg-blue-500': 'hsl(217, 91%, 60%)',
                    'bg-amber-500': 'hsl(38, 92%, 50%)',
                    'bg-slate-400': 'hsl(215, 14%, 62%)',
                    'bg-emerald-500': 'hsl(160, 84%, 39%)',
                    'bg-muted-foreground': 'hsl(var(--muted-foreground))',
                  }
                  return <Cell key={idx} fill={colorMap[entry.fill] ?? 'hsl(var(--primary))'} />
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

function QualityTierChart({ data }: { data: CollaborationPairDetail }) {
  const chartData = data.quality_tier_breakdown.map((item) => ({
    name: item.tier,
    value: item.count,
  }))

  const tierColorMap: Record<string, string> = {
    thorough: 'hsl(160, 84%, 39%)',
    standard: 'hsl(217, 91%, 60%)',
    rubber_stamp: 'hsl(0, 84%, 60%)',
    minimal: 'hsl(215, 14%, 62%)',
  }

  if (chartData.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Review Quality</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No reviews in this period.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">Review Quality</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ left: 20, right: 20, top: 5, bottom: 5 }}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {chartData.map((entry, idx) => (
                  <Cell key={idx} fill={tierColorMap[entry.name] ?? 'hsl(var(--primary))'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

type SortField = 'submitted_at' | 'quality_tier' | 'comment_count'
type SortDir = 'asc' | 'desc'

function SortTh({ field, current, asc, onToggle, children }: {
  field: SortField; current: SortField; asc: boolean; onToggle: (f: SortField) => void; children: React.ReactNode
}) {
  const active = field === current
  return (
    <th className="pb-2 pr-4">
      <button type="button" className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => onToggle(field)}>
        {children}
        {active && <span className="text-xs">{asc ? '\u2191' : '\u2193'}</span>}
      </button>
    </th>
  )
}

function RecentPRsTable({ data }: { data: CollaborationPairDetail }) {
  const [sortField, setSortField] = useState<SortField>('submitted_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const sorted = useMemo(() => {
    const prs = [...data.recent_prs]
    const dir = sortDir === 'asc' ? 1 : -1
    prs.sort((a, b) => {
      if (sortField === 'submitted_at') {
        return dir * ((a.submitted_at ?? '').localeCompare(b.submitted_at ?? ''))
      }
      if (sortField === 'comment_count') return dir * (a.comment_count - b.comment_count)
      if (sortField === 'quality_tier') return dir * (a.quality_tier.localeCompare(b.quality_tier))
      return 0
    })
    return prs
  }, [data.recent_prs, sortField, sortDir])

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  if (data.recent_prs.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">Reviewed PRs</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No PRs reviewed in this period.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">Reviewed PRs ({data.recent_prs.length})</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                <th className="pb-2 pr-4">PR</th>
                <th className="pb-2 pr-4">Repo</th>
                <SortTh field="submitted_at" current={sortField} asc={sortDir === 'asc'} onToggle={toggleSort}>Date</SortTh>
                <th className="pb-2 pr-4">State</th>
                <SortTh field="quality_tier" current={sortField} asc={sortDir === 'asc'} onToggle={toggleSort}>Quality</SortTh>
                <SortTh field="comment_count" current={sortField} asc={sortDir === 'asc'} onToggle={toggleSort}>Comments</SortTh>
                <th className="pb-2">Size</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((pr) => (
                <tr key={pr.pr_id} className="border-b border-border/50 last:border-0">
                  <td className="py-2 pr-4">
                    <span className="text-muted-foreground">#{pr.pr_number}</span>{' '}
                    <span className="font-medium">{pr.title}</span>
                  </td>
                  <td className="py-2 pr-4 text-xs text-muted-foreground">{pr.repo_full_name}</td>
                  <td className="py-2 pr-4 text-xs text-muted-foreground">
                    {pr.submitted_at ? new Date(pr.submitted_at).toLocaleDateString() : '-'}
                  </td>
                  <td className="py-2 pr-4">
                    <Badge variant="secondary" className={cn('text-[10px]',
                      pr.review_state === 'APPROVED' ? 'bg-emerald-500/10 text-emerald-600' :
                      pr.review_state === 'CHANGES_REQUESTED' ? 'bg-amber-500/10 text-amber-600' :
                      'bg-muted text-muted-foreground'
                    )}>
                      {pr.review_state ?? 'COMMENTED'}
                    </Badge>
                  </td>
                  <td className="py-2 pr-4">
                    <Badge variant="secondary" className={cn('text-[10px]', QUALITY_TIER_COLORS[pr.quality_tier] ?? '')}>
                      {pr.quality_tier}
                    </Badge>
                  </td>
                  <td className="py-2 pr-4 text-xs">{pr.comment_count}</td>
                  <td className="py-2 pr-4 text-xs text-muted-foreground">
                    {pr.additions != null && pr.deletions != null ? (
                      <span>
                        <span className="text-emerald-600">+{pr.additions}</span>
                        {' / '}
                        <span className="text-red-500">-{pr.deletions}</span>
                      </span>
                    ) : '-'}
                  </td>
                  <td className="py-2">
                    {pr.html_url && (
                      <a href={pr.html_url} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-foreground">
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
