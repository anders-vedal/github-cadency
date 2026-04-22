import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

interface Props {
  /** Combined AI share (reviewed + authored + hybrid) as a percentage 0..100. */
  aiSharePct: number | null | undefined
  /** Label variant — short by default; verbose is "X% AI-reviewed in range". */
  variant?: 'short' | 'verbose'
  /** Optional override of where "view cohort split" links to. */
  href?: string
}

/**
 * Phase 11 disclosure chip: surfaces the AI share of the dataset behind an
 * aggregate metric. Prevents readers from treating a blended number as a
 * clean human signal when a significant fraction came from AI-touched PRs.
 */
export default function AiCohortBadge({
  aiSharePct,
  variant = 'short',
  href = '/insights/dora',
}: Props) {
  if (aiSharePct == null) return null
  if (aiSharePct <= 0) return null

  const label =
    variant === 'verbose'
      ? `${aiSharePct.toFixed(0)}% AI-touched in range`
      : `${aiSharePct.toFixed(0)}% AI`

  return (
    <Tooltip>
      <TooltipTrigger className="inline-flex">
        <Link to={href} className="inline-flex">
          <Badge variant="outline" className="text-[10px]">
            {label}
          </Badge>
        </Link>
      </TooltipTrigger>
      <TooltipContent>
        AI-reviewed and AI-authored PRs blended in. Click to compare cohorts.
      </TooltipContent>
    </Tooltip>
  )
}
