import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AlertTriangle, ExternalLink } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import StatCard from '@/components/StatCard'
import ErrorCard from '@/components/ErrorCard'
import CommentBounceScatter from '@/components/charts/CommentBounceScatter'
import { useDateRange } from '@/hooks/useDateRange'
import { useIntegrations } from '@/hooks/useIntegrations'
import {
  useChattiestIssues,
  useCommentBounceScatter,
  useFirstResponseHistogram,
  useLinearLabels,
  useParticipantDistribution,
} from '@/hooks/useConversations'
import { useProjects } from '@/hooks/useSprints'

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}

function median(nums: number[]): number {
  if (nums.length === 0) return 0
  const sorted = [...nums].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid]
}

export default function IssueConversations() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: integrations } = useIntegrations()
  const hasLinear = integrations?.some(
    (i) => i.type === 'linear' && i.status === 'active',
  )

  const { data: projects } = useProjects()

  const [projectId, setProjectId] = useState<number | undefined>()
  const [creatorIdText, setCreatorIdText] = useState<string>('')
  const [priorityText, setPriorityText] = useState<string>('')
  const [hasLinkedPr, setHasLinkedPr] = useState<'all' | 'yes' | 'no'>('all')
  const [labelName, setLabelName] = useState<string>('')

  const { data: labelsData } = useLinearLabels(!!hasLinear)

  const filters = useMemo(
    () => ({
      dateFrom,
      dateTo,
      limit: 20,
      projectId,
      creatorId: creatorIdText ? Number(creatorIdText) : undefined,
      priority: priorityText ? Number(priorityText) : undefined,
      label: labelName || undefined,
      hasLinkedPr:
        hasLinkedPr === 'all' ? undefined : hasLinkedPr === 'yes',
    }),
    [
      dateFrom,
      dateTo,
      projectId,
      creatorIdText,
      priorityText,
      labelName,
      hasLinkedPr,
    ],
  )

  const {
    data: chattiest,
    isLoading: chattiestLoading,
    isError: chattiestError,
    refetch: refetchChattiest,
  } = useChattiestIssues(filters)
  const { data: scatter } = useCommentBounceScatter(dateFrom, dateTo)
  const { data: firstResponse } = useFirstResponseHistogram(dateFrom, dateTo)
  const { data: participants } = useParticipantDistribution(dateFrom, dateTo)

  // Summary stats derived from chattiest (note: in theory, we'd want these aggregated
  // server-side; the top-20 sample is a reasonable proxy for now)
  const summary = useMemo(() => {
    if (!chattiest || chattiest.length === 0) {
      return { total: 0, pctCommented: 0, medianComments: 0, medianFirstResponse: 0 }
    }
    const commentCounts = chattiest.map((c) => c.comment_count)
    const commented = chattiest.filter((c) => c.comment_count > 0).length
    const firstResponses = chattiest
      .map((c) => c.first_response_s)
      .filter((v): v is number => v != null)
    return {
      total: chattiest.length,
      pctCommented: Math.round((commented / chattiest.length) * 100),
      medianComments: median(commentCounts),
      medianFirstResponse: median(firstResponses),
    }
  }, [chattiest])

  if (!hasLinear) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Conversations</h1>
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <AlertTriangle className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No Linear integration configured</p>
              <p className="text-sm text-muted-foreground">
                Connect Linear to explore issue conversations.
              </p>
            </div>
            <Link
              to="/admin/integrations"
              className="text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
            >
              Go to Integration Settings &rarr;
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (chattiestError) {
    return <ErrorCard message="Could not load conversations data." onRetry={refetchChattiest} />
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Conversations</h1>
        <p className="text-sm text-muted-foreground">
          Where dialogue happens in Linear, and whether it correlates with bouncier PRs.
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 py-4">
          <div className="min-w-[180px] space-y-1">
            <Label className="text-xs text-muted-foreground">Project</Label>
            <Select
              value={projectId ? String(projectId) : '__all__'}
              onValueChange={(v) => setProjectId(v === '__all__' ? undefined : Number(v))}
            >
              <SelectTrigger>
                <SelectValue placeholder="All projects" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All projects</SelectItem>
                {projects?.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[140px] space-y-1">
            <Label className="text-xs text-muted-foreground">Creator ID</Label>
            <Input
              placeholder="e.g. 42"
              value={creatorIdText}
              onChange={(e) => setCreatorIdText(e.target.value)}
              className="h-9"
            />
          </div>
          <div className="min-w-[140px] space-y-1">
            <Label className="text-xs text-muted-foreground">Priority</Label>
            <Select
              value={priorityText || '__any__'}
              onValueChange={(v) =>
                setPriorityText(!v || v === '__any__' ? '' : v)
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Any" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__any__">Any priority</SelectItem>
                <SelectItem value="1">Urgent</SelectItem>
                <SelectItem value="2">High</SelectItem>
                <SelectItem value="3">Medium</SelectItem>
                <SelectItem value="4">Low</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[160px] space-y-1">
            <Label className="text-xs text-muted-foreground">Linked PR</Label>
            <Select
              value={hasLinkedPr}
              onValueChange={(v) => {
                if (v === 'all' || v === 'yes' || v === 'no') setHasLinkedPr(v)
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All issues</SelectItem>
                <SelectItem value="yes">Has linked PR</SelectItem>
                <SelectItem value="no">No linked PR</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[180px] space-y-1">
            <Label className="text-xs text-muted-foreground">Label</Label>
            <Select
              value={labelName || '__any__'}
              onValueChange={(v) =>
                setLabelName(!v || v === '__any__' ? '' : v)
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Any label" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__any__">Any label</SelectItem>
                {(labelsData?.labels ?? []).map((l) => (
                  <SelectItem key={l.name} value={l.name}>
                    {l.name}{' '}
                    <span className="text-muted-foreground">({l.count})</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {(projectId ||
            creatorIdText ||
            priorityText ||
            labelName ||
            hasLinkedPr !== 'all') && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setProjectId(undefined)
                setCreatorIdText('')
                setPriorityText('')
                setLabelName('')
                setHasLinkedPr('all')
              }}
            >
              Clear filters
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Summary stats */}
      {chattiestLoading ? (
        <div className="grid gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-4">
          <StatCard title="Issues (top 20)" value={summary.total} />
          <StatCard title="% Commented" value={`${summary.pctCommented}%`} />
          <StatCard
            title="Median Comments/Issue"
            value={summary.medianComments.toFixed(1)}
          />
          <StatCard
            title="Median First Response"
            value={formatDuration(summary.medianFirstResponse)}
          />
        </div>
      )}

      {/* Chattiness histograms */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Comments per issue</CardTitle>
          </CardHeader>
          <CardContent>
            <ChattinessHistogram data={chattiest ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Participants per issue</CardTitle>
          </CardHeader>
          <CardContent>
            {!participants || participants.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">No data</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={participants}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="participants" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar
                    dataKey="count"
                    name="Issues"
                    fill="hsl(var(--chart-2))"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Correlation scatter */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Chatter vs review rounds</CardTitle>
          <p className="text-xs text-muted-foreground">
            Do chatty issues produce bouncier PRs? One dot per (issue, linked PR) pair.
          </p>
        </CardHeader>
        <CardContent>
          <CommentBounceScatter points={scatter ?? []} />
        </CardContent>
      </Card>

      {/* Chattiest table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Chattiest issues</CardTitle>
        </CardHeader>
        <CardContent>
          {chattiestLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : !chattiest || chattiest.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No issues match the current filters.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Issue</TableHead>
                  <TableHead>Creator</TableHead>
                  <TableHead>Assignee</TableHead>
                  <TableHead>Project</TableHead>
                  <TableHead className="text-right">Comments</TableHead>
                  <TableHead className="text-right">People</TableHead>
                  <TableHead className="text-right">First resp.</TableHead>
                  <TableHead>Linked PRs</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {chattiest.map((row) => (
                  <TableRow key={row.issue_id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">
                          {row.identifier}
                        </span>
                        {row.url ? (
                          <a
                            href={row.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 truncate hover:underline"
                          >
                            {row.title}
                            <ExternalLink className="h-3 w-3 text-muted-foreground" />
                          </a>
                        ) : (
                          <span className="truncate">{row.title}</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs">
                      {row.creator?.name ?? '—'}
                    </TableCell>
                    <TableCell className="text-xs">
                      {row.assignee?.name ?? '—'}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {row.project?.name ?? '—'}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.comment_count}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {row.unique_participants}
                    </TableCell>
                    <TableCell className="text-right text-xs tabular-nums">
                      {formatDuration(row.first_response_s)}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {row.linked_prs.slice(0, 3).map((pr) => (
                          <Badge
                            key={pr.pr_id}
                            variant="outline"
                            className="font-mono text-[10px]"
                          >
                            #{pr.number}
                            {pr.review_round_count != null &&
                              ` · ${pr.review_round_count}r`}
                          </Badge>
                        ))}
                        {row.linked_prs.length > 3 && (
                          <Badge variant="outline" className="text-[10px]">
                            +{row.linked_prs.length - 3}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* First response histogram */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">First-response distribution</CardTitle>
          <p className="text-xs text-muted-foreground">
            How fast do issues get their first non-creator response?
          </p>
        </CardHeader>
        <CardContent>
          {!firstResponse || firstResponse.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No data</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={firstResponse}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar
                  dataKey="count"
                  name="Issues"
                  fill="hsl(var(--chart-1))"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function ChattinessHistogram({ data }: { data: { comment_count: number }[] }) {
  const buckets = useMemo(() => {
    const edges = [0, 1, 3, 5, 10, 20, Infinity]
    const labels = ['0', '1-2', '3-4', '5-9', '10-19', '20+']
    const counts = Array(labels.length).fill(0)
    for (const row of data) {
      for (let i = 0; i < edges.length - 1; i++) {
        if (row.comment_count >= edges[i] && row.comment_count < edges[i + 1]) {
          counts[i]++
          break
        }
      }
    }
    return labels.map((label, i) => ({ bucket: label, count: counts[i] }))
  }, [data])

  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No data</p>
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={buckets}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Bar
          dataKey="count"
          name="Issues"
          fill="hsl(var(--chart-1))"
          radius={[4, 4, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
