import { useMemo, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
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
import ErrorCard from '@/components/ErrorCard'
import type { ClassifierRule } from '@/hooks/useClassifierRules'
import {
  useClassifierRules,
  useCreateClassifierRule,
  useDeleteClassifierRule,
  useToggleClassifierRule,
} from '@/hooks/useClassifierRules'

type Kind = ClassifierRule['kind']

const INCIDENT_RULE_TYPES = [
  'pr_title_prefix',
  'revert_detection',
  'github_label',
  'linear_label',
  'linear_issue_type',
]
const AI_RULE_TYPES_REVIEWER = ['username']
const AI_RULE_TYPES_AUTHOR = ['label', 'email_pattern']

export default function ClassifierRulesPage() {
  const [kind, setKind] = useState<Kind>('incident')
  const { data, isLoading, isError, refetch } = useClassifierRules(kind)
  const create = useCreateClassifierRule()
  const del = useDeleteClassifierRule()
  const toggle = useToggleClassifierRule()

  const typeOptions = useMemo(() => {
    if (kind === 'incident') return INCIDENT_RULE_TYPES
    if (kind === 'ai_reviewer') return AI_RULE_TYPES_REVIEWER
    return AI_RULE_TYPES_AUTHOR
  }, [kind])

  const [form, setForm] = useState({
    rule_type: INCIDENT_RULE_TYPES[0],
    pattern: '',
    is_hotfix: false,
    is_incident: true,
    priority: 100,
  })

  // Reset form defaults when the kind tab switches so invalid rule_types don't leak.
  const switchKind = (k: Kind) => {
    setKind(k)
    if (k === 'incident') {
      setForm({
        rule_type: INCIDENT_RULE_TYPES[0],
        pattern: '',
        is_hotfix: false,
        is_incident: true,
        priority: 100,
      })
    } else if (k === 'ai_reviewer') {
      setForm({
        rule_type: AI_RULE_TYPES_REVIEWER[0],
        pattern: '',
        is_hotfix: false,
        is_incident: false,
        priority: 100,
      })
    } else {
      setForm({
        rule_type: AI_RULE_TYPES_AUTHOR[0],
        pattern: '',
        is_hotfix: false,
        is_incident: false,
        priority: 100,
      })
    }
  }

  const submit = () => {
    if (!form.pattern && form.rule_type !== 'revert_detection') {
      // revert_detection ignores the pattern; everything else needs something
      return
    }
    create.mutate({
      kind,
      rule_type: form.rule_type,
      pattern: form.pattern,
      is_hotfix: form.is_hotfix,
      is_incident: form.is_incident,
      priority: form.priority,
      enabled: true,
    })
    setForm((f) => ({ ...f, pattern: '' }))
  }

  if (isError) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Classifier Rules</h1>
        <ErrorCard
          message="Could not load classifier rules."
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Classifier Rules</h1>
        <p className="text-sm text-muted-foreground">
          Admin-editable rules for Change Failure Rate incident/hotfix detection
          and AI-cohort classification. Rules here add to the hard-coded
          defaults; they do not replace them.
        </p>
      </div>

      <div className="inline-flex rounded-md border p-0.5" role="tablist">
        {(['incident', 'ai_reviewer', 'ai_author'] as const).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={kind === k}
            onClick={() => switchKind(k)}
            className={
              kind === k
                ? 'rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground'
                : 'rounded px-3 py-1 text-xs font-medium text-muted-foreground hover:text-foreground'
            }
          >
            {k === 'incident'
              ? 'Incident / Hotfix'
              : k === 'ai_reviewer'
                ? 'AI Reviewers'
                : 'AI Authors'}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add rule</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="space-y-1">
              <Label className="text-xs">Rule type</Label>
              <Select
                value={form.rule_type}
                onValueChange={(v) =>
                  setForm((f) => ({ ...f, rule_type: v ?? f.rule_type }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {typeOptions.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label className="text-xs">Pattern</Label>
              <Input
                value={form.pattern}
                onChange={(e) =>
                  setForm((f) => ({ ...f, pattern: e.target.value }))
                }
                placeholder={
                  form.rule_type === 'revert_detection'
                    ? '(ignored)'
                    : 'e.g. hotfix:, sev-1, custombot[bot]'
                }
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Priority</Label>
              <Input
                type="number"
                value={form.priority}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    priority: Number(e.target.value) || 0,
                  }))
                }
              />
            </div>
            {kind === 'incident' && (
              <div className="flex items-center gap-4 sm:col-span-4">
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={form.is_hotfix}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, is_hotfix: e.target.checked }))
                    }
                  />
                  Hotfix
                </label>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={form.is_incident}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, is_incident: e.target.checked }))
                    }
                  />
                  Incident
                </label>
                <p className="text-xs text-muted-foreground">
                  One must be set. Incident &gt; Hotfix for CFR weighting.
                </p>
              </div>
            )}
            <div className="sm:col-span-4">
              <Button
                onClick={submit}
                disabled={create.isPending}
                size="sm"
              >
                {create.isPending ? 'Adding…' : 'Add rule'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Active rules</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading || !data ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Loading…
            </p>
          ) : data.rules.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              No custom rules for this kind. Defaults are still active.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Pattern</TableHead>
                  {kind === 'incident' && <TableHead>Flags</TableHead>}
                  <TableHead className="text-right">Priority</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-20"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rules.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono text-xs">
                      {r.rule_type}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {r.pattern || <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    {kind === 'incident' && (
                      <TableCell>
                        <div className="flex gap-1">
                          {r.is_incident && (
                            <Badge variant="destructive" className="text-[10px]">
                              incident
                            </Badge>
                          )}
                          {r.is_hotfix && (
                            <Badge variant="secondary" className="text-[10px]">
                              hotfix
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                    )}
                    <TableCell className="text-right tabular-nums">
                      {r.priority}
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        onClick={() =>
                          toggle.mutate({ id: r.id, enabled: !r.enabled })
                        }
                        className="text-xs underline underline-offset-2"
                      >
                        {r.enabled ? 'enabled' : 'disabled'}
                      </button>
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => del.mutate(r.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
