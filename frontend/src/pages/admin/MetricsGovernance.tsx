import { useMemo, useState } from 'react'
import { AlertTriangle, ShieldAlert } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import ErrorCard from '@/components/ErrorCard'
import MetricsUsageBanner from '@/components/MetricsUsageBanner'
import { useMetricsCatalog, type MetricSpec } from '@/hooks/useMetricsCatalog'

const VISIBILITY_LABEL: Record<MetricSpec['visibility_default'], string> = {
  self: 'Self + admin',
  team: 'Team',
  admin: 'Admin only',
}

const RISK_CLASS: Record<MetricSpec['goodhart_risk'], string> = {
  low: 'text-emerald-600 dark:text-emerald-400',
  medium: 'text-amber-600 dark:text-amber-400',
  high: 'text-red-600 dark:text-red-400',
}

export default function MetricsGovernance() {
  const { data, isLoading, isError, refetch } = useMetricsCatalog()
  const [categoryFilter, setCategoryFilter] = useState<string>('__all__')

  const categories = useMemo(() => {
    if (!data) return []
    return Array.from(new Set(data.metrics.map((m) => m.category))).sort()
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    if (categoryFilter === '__all__') return data.metrics
    return data.metrics.filter((m) => m.category === categoryFilter)
  }, [data, categoryFilter])

  if (isError) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Metrics Governance</h1>
        <ErrorCard
          message="Could not load the metrics catalog."
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Metrics Governance</h1>
        <p className="text-sm text-muted-foreground">
          Every metric DevPulse surfaces, its visibility default, and the Goodhart
          risk of optimizing it directly. See{' '}
          <code className="text-xs">docs/metrics/principles.md</code> for the rationale.
        </p>
      </div>

      <MetricsUsageBanner />

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Registered metrics</CardTitle>
            <select
              className="rounded-md border bg-background px-2 py-1 text-xs"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            >
              <option value="__all__">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading || !data ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Loading catalog…
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metric</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Shape</TableHead>
                  <TableHead>Paired outcome</TableHead>
                  <TableHead>Visibility</TableHead>
                  <TableHead>Goodhart risk</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((m) => (
                  <TableRow key={m.key}>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">{m.label}</span>
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {m.key}
                        </span>
                        {m.description && (
                          <span className="text-xs text-muted-foreground">
                            {m.description}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs capitalize">
                      {m.category}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-0.5">
                        <Badge
                          variant={m.is_activity ? 'default' : 'secondary'}
                          className="w-fit text-[10px]"
                        >
                          {m.is_activity ? 'activity' : 'outcome'}
                        </Badge>
                        {m.is_distribution && (
                          <Badge variant="outline" className="w-fit text-[10px]">
                            distribution
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {m.paired_outcome_key ?? '—'}
                    </TableCell>
                    <TableCell className="text-xs">
                      {VISIBILITY_LABEL[m.visibility_default]}
                    </TableCell>
                    <TableCell>
                      <div className={RISK_CLASS[m.goodhart_risk]}>
                        <span className="text-xs font-semibold capitalize">
                          {m.goodhart_risk}
                        </span>
                      </div>
                      {m.goodhart_notes && (
                        <div className="mt-0.5 max-w-xs text-[11px] text-muted-foreground">
                          {m.goodhart_notes}
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-red-500" />
            <CardTitle className="text-base">Banned metrics</CardTitle>
          </div>
          <p className="text-xs text-muted-foreground">
            Metrics DevPulse deliberately does not expose. See{' '}
            <code className="text-xs">docs/metrics/banned.md</code>.
          </p>
        </CardHeader>
        <CardContent>
          {isLoading || !data ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Loading…
            </p>
          ) : data.banned.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No entries.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.banned.map((b) => (
                <li key={b.key} className="flex gap-2 text-sm">
                  <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-500" />
                  <div>
                    <code className="text-xs">{b.key}</code>
                    <p className="mt-0.5 text-xs text-muted-foreground">{b.reason}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
