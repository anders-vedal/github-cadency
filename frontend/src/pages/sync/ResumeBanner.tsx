import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { AlertTriangle } from 'lucide-react'
import { useResumeSync } from '@/hooks/useSync'
import type { SyncEvent } from '@/utils/types'

interface ResumeBannerProps {
  event: SyncEvent
  onStartFresh: () => void
}

export default function ResumeBanner({ event, onStartFresh }: ResumeBannerProps) {
  const resumeSync = useResumeSync()

  const completed = event.repos_completed?.length ?? 0
  const total = event.total_repos ?? 0
  const failed = event.repos_failed?.length ?? 0
  const remaining = total - completed

  return (
    <Card className="border-amber-500/30 bg-amber-500/5">
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <div>
            <div className="text-sm font-medium">
              Previous sync was interrupted after {completed}/{total} repos.
            </div>
            <div className="text-xs text-muted-foreground">
              {remaining} repos remaining
              {failed > 0 && `, ${failed} failed`}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => resumeSync.mutate(event.id)}
            disabled={resumeSync.isPending}
          >
            Resume Sync
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onStartFresh}
          >
            Start Fresh
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
