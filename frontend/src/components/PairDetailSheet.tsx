import { Link } from 'react-router-dom'
import { useDateRange } from '@/hooks/useDateRange'
import { useCollaborationPairDetail } from '@/hooks/useStats'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import type { CollaborationPairDetail, PairRelationship } from '@/utils/types'
import { ArrowRight, ExternalLink } from 'lucide-react'

const RELATIONSHIP_COLORS: Record<string, string> = {
  mentor: 'bg-purple-500/10 text-purple-600',
  peer: 'bg-emerald-500/10 text-emerald-600',
  gatekeeper: 'bg-orange-500/10 text-orange-600',
  rubber_stamp: 'bg-red-500/10 text-red-600',
  one_way_dependency: 'bg-amber-500/10 text-amber-600',
  casual: 'bg-muted text-muted-foreground',
  none: 'bg-muted text-muted-foreground',
}

const RELATIONSHIP_LABELS: Record<string, string> = {
  mentor: 'Mentor',
  peer: 'Peer',
  gatekeeper: 'Gatekeeper',
  rubber_stamp: 'Rubber Stamp',
  one_way_dependency: 'One-Way Dependency',
  casual: 'Casual',
  none: 'No Interaction',
}

const QUALITY_TIER_COLORS: Record<string, string> = {
  thorough: 'bg-emerald-500/10 text-emerald-600',
  standard: 'bg-blue-500/10 text-blue-600',
  rubber_stamp: 'bg-red-500/10 text-red-600',
  minimal: 'bg-muted text-muted-foreground',
}

const COMMENT_TYPE_COLORS: Record<string, string> = {
  blocker: 'bg-red-500',
  architectural: 'bg-purple-500',
  suggestion: 'bg-blue-500',
  question: 'bg-amber-500',
  nit: 'bg-slate-400',
  praise: 'bg-emerald-500',
  general: 'bg-muted-foreground',
}

function RelationshipBadge({ relationship }: { relationship: PairRelationship }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className={cn('text-xs', RELATIONSHIP_COLORS[relationship.label] ?? RELATIONSHIP_COLORS.none)}>
          {RELATIONSHIP_LABELS[relationship.label] ?? relationship.label}
        </Badge>
        <span className="text-[10px] text-muted-foreground">
          {Math.round(relationship.confidence * 100)}% confidence
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{relationship.explanation}</p>
    </div>
  )
}

function CommentTypeBar({ breakdown, total }: { breakdown: { comment_type: string; count: number }[]; total: number }) {
  if (total === 0) return <p className="text-xs text-muted-foreground">No comments</p>

  return (
    <div className="space-y-1.5">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {breakdown.map((item) => (
          <div
            key={item.comment_type}
            className={cn('h-full', COMMENT_TYPE_COLORS[item.comment_type] ?? 'bg-muted-foreground')}
            style={{ width: `${(item.count / total) * 100}%` }}
            title={`${item.comment_type}: ${item.count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {breakdown.map((item) => (
          <span key={item.comment_type} className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <span className={cn('inline-block h-2 w-2 rounded-full', COMMENT_TYPE_COLORS[item.comment_type] ?? 'bg-muted-foreground')} />
            {item.comment_type} ({item.count})
          </span>
        ))}
      </div>
    </div>
  )
}

function SheetBody({ data }: { data: CollaborationPairDetail }) {
  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-4 pb-4">
      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-md border p-2">
          <p className="text-[10px] text-muted-foreground">Reviews</p>
          <p className="text-lg font-semibold">{data.total_reviews}</p>
        </div>
        <div className="rounded-md border p-2">
          <p className="text-[10px] text-muted-foreground">Approval Rate</p>
          <p className="text-lg font-semibold">{Math.round(data.approval_rate * 100)}%</p>
        </div>
        <div className="rounded-md border p-2">
          <p className="text-[10px] text-muted-foreground">Avg Quality</p>
          <Badge variant="secondary" className={cn('text-xs mt-0.5', QUALITY_TIER_COLORS[data.avg_quality_tier] ?? '')}>
            {data.avg_quality_tier}
          </Badge>
        </div>
        <div className="rounded-md border p-2">
          <p className="text-[10px] text-muted-foreground">Comments</p>
          <p className="text-lg font-semibold">{data.total_comments}</p>
        </div>
      </div>

      {/* Relationship */}
      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Relationship</p>
        <RelationshipBadge relationship={data.relationship} />
      </div>

      {/* Comment types */}
      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Comment Types</p>
        <CommentTypeBar breakdown={data.comment_type_breakdown} total={data.total_comments} />
      </div>

      {/* Recent PRs (first 5) */}
      {data.recent_prs.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Recent PRs</p>
          <ul className="space-y-1.5">
            {data.recent_prs.slice(0, 5).map((pr) => (
              <li key={pr.pr_id} className="flex items-start justify-between gap-2 text-xs">
                <div className="min-w-0 flex-1">
                  <span className="text-muted-foreground">#{pr.pr_number}</span>{' '}
                  <span className="font-medium">{pr.title}</span>
                  <span className="ml-1 text-muted-foreground">{pr.repo_full_name}</span>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Badge variant="secondary" className={cn('text-[9px]', QUALITY_TIER_COLORS[pr.quality_tier] ?? '')}>
                    {pr.quality_tier}
                  </Badge>
                  {pr.html_url && (
                    <a href={pr.html_url} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-foreground">
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Link to full page */}
      <Link
        to={`/insights/collaboration/${data.reviewer_id}/${data.author_id}`}
        className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
      >
        View full detail <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  )
}

interface PairDetailSheetProps {
  reviewerId: number | null
  authorId: number | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function PairDetailSheet({ reviewerId, authorId, open, onOpenChange }: PairDetailSheetProps) {
  const { dateFrom, dateTo } = useDateRange()
  const { data, isLoading } = useCollaborationPairDetail(
    open ? reviewerId : null,
    open ? authorId : null,
    dateFrom,
    dateTo,
  )

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>
            {data ? (
              <span className="flex items-center gap-1.5 text-sm">
                {data.reviewer_name} <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" /> {data.author_name}
              </span>
            ) : (
              'Pair Detail'
            )}
          </SheetTitle>
          <SheetDescription>
            Review interactions between this pair
          </SheetDescription>
        </SheetHeader>

        {isLoading ? (
          <div className="space-y-3 px-4">
            <Skeleton className="h-20 w-full rounded-md" />
            <Skeleton className="h-12 w-full rounded-md" />
            <Skeleton className="h-32 w-full rounded-md" />
          </div>
        ) : data ? (
          data.total_reviews === 0 ? (
            <div className="px-4 py-8 text-center">
              <p className="text-sm text-muted-foreground">No review interactions between these developers in this period.</p>
            </div>
          ) : (
            <SheetBody data={data} />
          )
        ) : null}
      </SheetContent>
    </Sheet>
  )
}

export { RelationshipBadge, CommentTypeBar, RELATIONSHIP_COLORS, RELATIONSHIP_LABELS, QUALITY_TIER_COLORS, COMMENT_TYPE_COLORS }
