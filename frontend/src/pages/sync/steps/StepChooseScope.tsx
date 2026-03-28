import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Zap, Settings2 } from 'lucide-react'

interface StepChooseScopeProps {
  onQuickSync: () => void
  onCustomSync: () => void
  disabled: boolean
}

export default function StepChooseScope({ onQuickSync, onCustomSync, disabled }: StepChooseScopeProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card className="cursor-pointer transition-all hover:ring-2 hover:ring-primary/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            Quick Sync
          </CardTitle>
          <CardDescription>
            Fetch changes since each repo's last sync. Fast, typically under 5 minutes.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            className="w-full"
            onClick={onQuickSync}
            disabled={disabled}
          >
            Start Quick Sync
          </Button>
        </CardContent>
      </Card>

      <Card className="cursor-pointer transition-all hover:ring-2 hover:ring-primary/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5 text-muted-foreground" />
            Custom Sync
          </CardTitle>
          <CardDescription>
            Choose specific repos, time range, and scope for a tailored sync.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            className="w-full"
            variant="outline"
            onClick={onCustomSync}
            disabled={disabled}
          >
            Configure Custom Sync
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
