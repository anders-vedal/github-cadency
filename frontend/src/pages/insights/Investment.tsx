import { useMemo, useState, useId } from 'react'
import { toast } from 'sonner'
import { useDateRange } from '@/hooks/useDateRange'
import { useWorkAllocation } from '@/hooks/useStats'
import StatCard from '@/components/StatCard'
import StatCardSkeleton from '@/components/StatCardSkeleton'
import TableSkeleton from '@/components/TableSkeleton'
import ErrorCard from '@/components/ErrorCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Switch } from '@/components/ui/switch'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from 'recharts'
import { HelpCircle, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAISettings } from '@/hooks/useAISettings'
import type { WorkCategory } from '@/utils/types'
import { CATEGORY_CONFIG, CATEGORY_ORDER } from '@/utils/categoryConfig'

const tooltipStyle = {
  backgroundColor: 'hsl(var(--card))',
  border: '1px solid hsl(var(--border))',
  borderRadius: '6px',
  fontSize: '12px',
}

export default function Investment() {
  const { dateFrom, dateTo } = useDateRange()
  const [useAi, setUseAi] = useState(false)
  const { data: aiSettings } = useAISettings()
  const { data, isLoading, isError, refetch } = useWorkAllocation(
    undefined,
    dateFrom,
    dateTo,
    useAi,
  )
  const pieId = useId()

  const prDonutData = useMemo(() => {
    if (!data) return []
    return data.pr_allocation
      .filter((a) => a.count > 0)
      .map((a) => ({
        name: CATEGORY_CONFIG[a.category]?.label ?? a.category,
        value: a.count,
        color: CATEGORY_CONFIG[a.category]?.color ?? '#94a3b8',
        pct: a.pct_of_total,
      }))
  }, [data])

  const issueDonutData = useMemo(() => {
    if (!data) return []
    return data.issue_allocation
      .filter((a) => a.count > 0)
      .map((a) => ({
        name: CATEGORY_CONFIG[a.category]?.label ?? a.category,
        value: a.count,
        color: CATEGORY_CONFIG[a.category]?.color ?? '#94a3b8',
        pct: a.pct_of_total,
      }))
  }, [data])

  const trendData = useMemo(() => {
    if (!data) return []
    return data.trend.map((p) => ({
      label: p.period_label,
      ...Object.fromEntries(
        CATEGORY_ORDER.map((cat) => [cat, p.pr_categories[cat] ?? 0]),
      ),
    }))
  }, [data])

  const [sortKey, setSortKey] = useState<'total_prs' | 'total_issues' | WorkCategory>('total_prs')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

  const sortedDevs = useMemo(() => {
    if (!data) return []
    return [...data.developer_breakdown].sort((a, b) => {
      let va: number, vb: number
      if (sortKey === 'total_prs') {
        va = a.total_prs; vb = b.total_prs
      } else if (sortKey === 'total_issues') {
        va = a.total_issues; vb = b.total_issues
      } else {
        va = (a.pr_categories[sortKey] ?? 0); vb = (b.pr_categories[sortKey] ?? 0)
      }
      return sortDir === 'desc' ? vb - va : va - vb
    })
  }, [data, sortKey, sortDir])

  function toggleSort(key: typeof sortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  if (isError) {
    return <ErrorCard message="Failed to load work allocation data." onRetry={refetch} />
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Engineering Investment</h1>
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Card><CardContent className="h-[300px]" /></Card>
          <Card><CardContent className="h-[300px]" /></Card>
        </div>
        <Card><CardContent className="h-[300px]" /></Card>
        <TableSkeleton rows={5} cols={7} />
      </div>
    )
  }

  if (!data || (data.total_prs === 0 && data.total_issues === 0)) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Engineering Investment</h1>
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No merged PRs or issues found in this period.
          </CardContent>
        </Card>
      </div>
    )
  }

  const totalPrCount = prDonutData.reduce((s, d) => s + d.value, 0)
  const totalIssueCount = issueDonutData.reduce((s, d) => s + d.value, 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Engineering Investment</h1>
          <Tooltip>
            <TooltipTrigger>
              <HelpCircle className="h-4 w-4 text-muted-foreground" />
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              <p>Classifies merged PRs and created issues into categories using GitHub labels, title keywords, and optionally AI. Shows where engineering effort is going.</p>
            </TooltipContent>
          </Tooltip>
        </div>
        <div className="flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-2">
                <Sparkles className={cn('h-4 w-4', useAi ? 'text-primary' : 'text-muted-foreground')} />
                <Switch
                  checked={useAi}
                  onCheckedChange={(checked) => {
                    if (checked && aiSettings && !aiSettings.feature_work_categorization) {
                      toast.error('AI classification is disabled. Enable it in AI Settings.')
                      return
                    }
                    setUseAi(checked)
                  }}
                  disabled={isLoading}
                />
                <span className="text-sm text-muted-foreground">AI Classify</span>
              </div>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              <p>Uses Claude API to classify items that couldn't be determined from labels or title keywords. Requires ANTHROPIC_API_KEY.</p>
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          title="Merged PRs"
          value={data.total_prs}
          tooltip="Total merged pull requests in the selected period, classified by work category."
        />
        <StatCard
          title="Issues Created"
          value={data.total_issues}
          tooltip="Total issues created by team members in the selected period."
        />
        <StatCard
          title="Unclassified"
          value={`${data.unknown_pct}%`}
          tooltip="Percentage of items that couldn't be classified by labels or title keywords."
          subtitle={useAi && data.ai_classified_count > 0 ? `${data.ai_classified_count} AI-classified` : undefined}
        />
      </div>

      {/* Donut charts */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              PR Allocation by Category
            </CardTitle>
          </CardHeader>
          <CardContent>
            {prDonutData.length === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">No PR data.</p>
            ) : (
              <>
                <div className="relative">
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie
                        data={prDonutData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={80}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {prDonutData.map((entry) => (
                          <Cell key={`${pieId}-pr-${entry.name}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <RechartsTooltip
                        contentStyle={tooltipStyle}
                        formatter={(value: number, name: string) => [
                          `${value} (${((value / totalPrCount) * 100).toFixed(0)}%)`,
                          name,
                        ]}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-center">
                      <div className="text-2xl font-bold">{totalPrCount}</div>
                      <div className="text-[10px] text-muted-foreground">PRs</div>
                    </div>
                  </div>
                </div>
                <CategoryLegend data={prDonutData} />
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Issue Allocation by Category
            </CardTitle>
          </CardHeader>
          <CardContent>
            {issueDonutData.length === 0 ? (
              <p className="text-sm text-muted-foreground py-8 text-center">No issue data.</p>
            ) : (
              <>
                <div className="relative">
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie
                        data={issueDonutData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={80}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {issueDonutData.map((entry) => (
                          <Cell key={`${pieId}-issue-${entry.name}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <RechartsTooltip
                        contentStyle={tooltipStyle}
                        formatter={(value: number, name: string) => [
                          `${value} (${((value / totalIssueCount) * 100).toFixed(0)}%)`,
                          name,
                        ]}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-center">
                      <div className="text-2xl font-bold">{totalIssueCount}</div>
                      <div className="text-[10px] text-muted-foreground">Issues</div>
                    </div>
                  </div>
                </div>
                <CategoryLegend data={issueDonutData} />
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Trend chart */}
      {trendData.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Investment Over Time ({data.period_type === 'weekly' ? 'Weekly' : 'Monthly'})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="label" fontSize={12} stroke="hsl(var(--muted-foreground))" />
                <YAxis fontSize={12} stroke="hsl(var(--muted-foreground))" />
                <RechartsTooltip contentStyle={tooltipStyle} />
                <Legend />
                {CATEGORY_ORDER.filter((cat) => cat !== 'unknown').map((cat) => (
                  <Bar
                    key={cat}
                    dataKey={cat}
                    stackId="a"
                    name={CATEGORY_CONFIG[cat].label}
                    fill={CATEGORY_CONFIG[cat].color}
                  />
                ))}
                <Bar
                  dataKey="unknown"
                  stackId="a"
                  name={CATEGORY_CONFIG.unknown.label}
                  fill={CATEGORY_CONFIG.unknown.color}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Developer breakdown */}
      {sortedDevs.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Developer Breakdown
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Developer</TableHead>
                  <TableHead className="cursor-pointer" onClick={() => toggleSort('total_prs')}>
                    PRs {sortKey === 'total_prs' ? (sortDir === 'desc' ? '↓' : '↑') : ''}
                  </TableHead>
                  {CATEGORY_ORDER.map((cat) => (
                    <TableHead
                      key={cat}
                      className="cursor-pointer text-center"
                      onClick={() => toggleSort(cat)}
                    >
                      <span style={{ color: CATEGORY_CONFIG[cat].color }}>
                        {CATEGORY_CONFIG[cat].label}
                      </span>
                      {sortKey === cat ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
                    </TableHead>
                  ))}
                  <TableHead className="cursor-pointer" onClick={() => toggleSort('total_issues')}>
                    Issues {sortKey === 'total_issues' ? (sortDir === 'desc' ? '↓' : '↑') : ''}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedDevs.map((dev) => {
                  const maxCat = CATEGORY_ORDER.reduce(
                    (max, cat) =>
                      (dev.pr_categories[cat] ?? 0) > (dev.pr_categories[max] ?? 0) ? cat : max,
                    CATEGORY_ORDER[0],
                  )
                  return (
                    <TableRow key={dev.developer_id}>
                      <TableCell>
                        <div>
                          <div className="font-medium">{dev.display_name}</div>
                          {dev.team && (
                            <div className="text-xs text-muted-foreground">{dev.team}</div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>{dev.total_prs}</TableCell>
                      {CATEGORY_ORDER.map((cat) => {
                        const count = dev.pr_categories[cat] ?? 0
                        const pct =
                          dev.total_prs > 0 ? Math.round((count / dev.total_prs) * 100) : 0
                        return (
                          <TableCell key={cat} className="text-center">
                            {count > 0 ? (
                              <div className="flex flex-col items-center gap-0.5">
                                <span>{count}</span>
                                <div
                                  className="h-1 rounded-full"
                                  style={{
                                    width: `${Math.max(pct, 4)}%`,
                                    backgroundColor: CATEGORY_CONFIG[cat].color,
                                    minWidth: count > 0 ? '4px' : '0px',
                                  }}
                                />
                              </div>
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </TableCell>
                        )
                      })}
                      <TableCell>{dev.total_issues}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function CategoryLegend({ data }: { data: { name: string; value: number; color: string }[] }) {
  return (
    <div className="mt-2 flex flex-wrap justify-center gap-3">
      {data.map((d) => (
        <div key={d.name} className="flex items-center gap-1.5 text-xs">
          <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: d.color }} />
          <span className="text-muted-foreground">
            {d.name} ({d.value})
          </span>
        </div>
      ))}
    </div>
  )
}
