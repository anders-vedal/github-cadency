import { useState, useCallback, useRef } from 'react'
import { useSlackUserSettings, useUpdateSlackUserSettings } from '@/hooks/useSlack'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Bell } from 'lucide-react'
import type { SlackUserSettingsUpdate } from '@/utils/types'

const NOTIFICATION_TOGGLES = [
  { key: 'notify_stale_prs' as const, label: 'Stale PR nudges' },
  { key: 'notify_high_risk_prs' as const, label: 'High-risk PR alerts' },
  { key: 'notify_workload_alerts' as const, label: 'Workload alerts' },
  { key: 'notify_weekly_digest' as const, label: 'Weekly digest' },
]

export default function SlackPreferencesSection({
  isOwnPage,
}: {
  isOwnPage: boolean
}) {
  const { data: settings, isLoading } = useSlackUserSettings()
  const updateSettings = useUpdateSlackUserSettings()

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const save = useCallback(
    (updates: SlackUserSettingsUpdate) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => updateSettings.mutate(updates), 500)
    },
    [updateSettings],
  )

  const saveNow = useCallback(
    (updates: SlackUserSettingsUpdate) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      updateSettings.mutate(updates)
    },
    [updateSettings],
  )

  // Only show for the user's own profile (user settings endpoint uses current user)
  if (!isOwnPage) return null
  if (isLoading || !settings) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm font-medium">Slack Notifications</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label className="text-xs">Your Slack User ID</Label>
          <SlackUserIdInput
            value={settings.slack_user_id ?? ''}
            onSave={(val) => save({ slack_user_id: val || null })}
          />
          <p className="text-xs text-muted-foreground mt-1">
            Find this in Slack: click your profile, then "Copy member ID".
          </p>
        </div>

        {settings.slack_user_id && (
          <div className="space-y-2">
            {NOTIFICATION_TOGGLES.map((nt) => (
              <div key={nt.key} className="flex items-center justify-between">
                <span className="text-sm">{nt.label}</span>
                <Switch
                  checked={settings[nt.key]}
                  onCheckedChange={(checked) => saveNow({ [nt.key]: checked })}
                />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function SlackUserIdInput({
  value,
  onSave,
}: {
  value: string
  onSave: (val: string) => void
}) {
  const [input, setInput] = useState(value)
  return (
    <Input
      placeholder="U0123456789"
      value={input}
      onChange={(e) => {
        setInput(e.target.value)
        onSave(e.target.value.trim())
      }}
      className="mt-1 max-w-xs"
    />
  )
}
