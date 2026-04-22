import { Link } from 'react-router-dom'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { LinearHealthCreatorRow } from '@/utils/types'

interface CreatorOutcomeMiniTableProps {
  creators: LinearHealthCreatorRow[]
  minSampleSize?: number
}

export default function CreatorOutcomeMiniTable({
  creators,
  minSampleSize = 5,
}: CreatorOutcomeMiniTableProps) {
  const top = creators.slice(0, 3)
  if (top.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No creator activity in this range yet.
      </p>
    )
  }

  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 text-[10px] uppercase tracking-wider text-muted-foreground">
        <span>Creator</span>
        <span className="text-right">Issues</span>
        <span className="text-right">Avg rounds</span>
      </div>
      {top.map((c) => {
        const lowSample = c.sample_size < minSampleSize
        return (
          <div
            key={c.developer_id}
            className="grid grid-cols-[1fr_auto_auto] items-center gap-x-3 text-xs"
          >
            <Link
              to={`/team/${c.developer_id}`}
              className="truncate font-medium hover:underline"
            >
              {c.developer_name}
            </Link>
            <span className="text-right tabular-nums">{c.issues_created}</span>
            <span className="flex items-center justify-end gap-1 text-right tabular-nums">
              {lowSample ? (
                <Tooltip>
                  <TooltipTrigger className="inline-flex items-center gap-1">
                    <span className="text-muted-foreground">
                      {c.avg_downstream_pr_review_rounds.toFixed(1)}
                    </span>
                    <span className="rounded bg-amber-500/15 px-1 text-[10px] font-medium text-amber-700 dark:text-amber-300">
                      n={c.sample_size}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    Only {c.sample_size} linked PR{c.sample_size === 1 ? '' : 's'} — not
                    enough data for a confident signal
                  </TooltipContent>
                </Tooltip>
              ) : (
                <span>{c.avg_downstream_pr_review_rounds.toFixed(1)}</span>
              )}
            </span>
          </div>
        )
      })}
    </div>
  )
}
