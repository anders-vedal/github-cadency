import { Link } from 'react-router-dom'
import {
  FileText,
  GitPullRequest,
  Link2,
  MessageSquare,
  UserCheck,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useLinearUsageHealth } from '@/hooks/useLinearUsageHealth'
import { useDateRange } from '@/hooks/useDateRange'
import { ApiError } from '@/utils/api'
import type { LinearHealthStatus } from '@/utils/types'
import CreatorOutcomeMiniTable from './CreatorOutcomeMiniTable'

const STATUS_STYLES: Record<LinearHealthStatus, string> = {
  healthy: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  critical: 'bg-red-500/10 text-red-600 dark:text-red-400',
}

const STATUS_LABEL: Record<LinearHealthStatus, string> = {
  healthy: 'Healthy',
  warning: 'Warning',
  critical: 'Critical',
}

function StatusPill({ status }: { status: LinearHealthStatus }) {
  return (
    <span
      className={cn(
        'rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
        STATUS_STYLES[status],
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}

interface SignalRowProps {
  icon: React.ReactNode
  title: string
  headline: string
  narrative: string
  status: LinearHealthStatus
  to: string
  children?: React.ReactNode
}

function SignalRow({ icon, title, headline, narrative, status, to, children }: SignalRowProps) {
  return (
    <Link
      to={to}
      className="-mx-2 block rounded-md px-2 py-2 transition-colors hover:bg-muted/50"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted">
          {icon}
        </div>
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {title}
            </span>
            <StatusPill status={status} />
          </div>
          <p className="text-sm">
            <span className="font-semibold">{headline}</span>
            <span className="ml-1 text-muted-foreground">{narrative}</span>
          </p>
          {children}
        </div>
      </div>
    </Link>
  )
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}

export default function LinearUsageHealthCard() {
  const { dateFrom, dateTo } = useDateRange()
  const { data, isLoading, isError, error } = useLinearUsageHealth(dateFrom, dateTo)

  // 409 = Linear not configured as primary — hide the card, don't show an error
  if (error instanceof ApiError && error.status === 409) return null

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Linear Usage Health</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </CardContent>
      </Card>
    )
  }

  if (isError) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Linear Usage Health</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Couldn&rsquo;t load Linear usage health.{' '}
            {error instanceof Error ? error.message : 'Try refreshing.'}
          </p>
        </CardContent>
      </Card>
    )
  }
  if (!data) {
    return null
  }

  const { adoption, spec_quality, autonomy, dialogue_health, creator_outcome } = data

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Linear Usage Health</CardTitle>
        <p className="text-xs text-muted-foreground">
          How much real work flows through Linear — five signals for self-reflection.
        </p>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {/* Adoption */}
        <SignalRow
          icon={<Link2 className="h-3.5 w-3.5" />}
          title="Adoption"
          headline={`${Math.round(adoption.linkage_rate * 100)}% of merged PRs linked`}
          narrative={`(${adoption.linked_pr_count}/${adoption.total_pr_count})`}
          status={adoption.status}
          to="/admin/linkage-quality"
        />

        {/* Spec quality */}
        <SignalRow
          icon={<FileText className="h-3.5 w-3.5" />}
          title="Spec Quality"
          headline={`Median description ${spec_quality.median_description_length} chars`}
          narrative={`(${spec_quality.median_comments_before_first_pr.toFixed(1)} comments/issue)`}
          status={spec_quality.status}
          to="/insights/conversations"
        />

        {/* Autonomy */}
        <SignalRow
          icon={<UserCheck className="h-3.5 w-3.5" />}
          title="Autonomy"
          headline={`${Math.round(autonomy.self_picked_pct * 100)}% self-picked`}
          narrative={`(${autonomy.self_picked_count} self / ${autonomy.pushed_count} pushed; time-to-assign ${formatDuration(autonomy.median_time_to_assign_s)})`}
          status={autonomy.status}
          to="/insights/planning"
        />

        {/* Dialogue */}
        <SignalRow
          icon={<MessageSquare className="h-3.5 w-3.5" />}
          title="Dialogue"
          headline={`Median ${dialogue_health.median_comments_per_issue.toFixed(1)} comments/issue`}
          narrative={`(p90 ${dialogue_health.p90_comments_per_issue}; ${Math.round(dialogue_health.silent_issue_pct * 100)}% silent)`}
          status={dialogue_health.status}
          to="/insights/conversations"
        />

        {/* Creator outcome — a bit different; renders mini-table inline */}
        <div className="-mx-2 rounded-md px-2 py-2">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted">
              <GitPullRequest className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Ticket Clarity Signal
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Who's shipping tickets that flow cleanly through review?
              </p>
              <CreatorOutcomeMiniTable creators={creator_outcome.top_creators} />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
