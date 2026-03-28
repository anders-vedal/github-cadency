import { useState } from 'react'
import { useAIHistory, useRunAnalysis } from '@/hooks/useAI'
import { useDevelopers } from '@/hooks/useDevelopers'
import { useRepos } from '@/hooks/useSync'
import { useDateRange } from '@/hooks/useDateRange'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { AIAnalyzeRequest } from '@/utils/types'

export default function AIAnalysis() {
  const { dateFrom, dateTo } = useDateRange()
  const { data: history, isLoading } = useAIHistory()
  const runAnalysis = useRunAnalysis()
  const { data: developers } = useDevelopers()
  const { data: repos } = useRepos()

  const [open, setOpen] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [form, setForm] = useState<AIAnalyzeRequest>({
    analysis_type: 'communication',
    scope_type: 'developer',
    scope_id: '',
    date_from: '',
    date_to: '',
  })

  const teams = [...new Set((developers ?? []).map((d) => d.team).filter(Boolean))] as string[]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">AI Analysis</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>New Analysis</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Run AI Analysis</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Analysis Type</label>
                <select
                  className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
                  value={form.analysis_type}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      analysis_type: e.target.value as AIAnalyzeRequest['analysis_type'],
                    })
                  }
                >
                  <option value="communication">Communication</option>
                  <option value="conflict">Conflict</option>
                  <option value="sentiment">Sentiment</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium">Scope</label>
                <select
                  className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
                  value={form.scope_type}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      scope_type: e.target.value as AIAnalyzeRequest['scope_type'],
                      scope_id: '',
                    })
                  }
                >
                  <option value="developer">Developer</option>
                  <option value="team">Team</option>
                  <option value="repo">Repository</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium">
                  {form.scope_type === 'developer'
                    ? 'Developer'
                    : form.scope_type === 'team'
                      ? 'Team'
                      : 'Repository'}
                </label>
                <select
                  className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
                  value={form.scope_id}
                  onChange={(e) => setForm({ ...form, scope_id: e.target.value })}
                >
                  <option value="">Select...</option>
                  {form.scope_type === 'developer' &&
                    (developers ?? []).map((d) => (
                      <option key={d.id} value={String(d.id)}>
                        {d.display_name} (@{d.github_username})
                      </option>
                    ))}
                  {form.scope_type === 'team' &&
                    teams.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  {form.scope_type === 'repo' &&
                    (repos ?? []).map((r) => (
                      <option key={r.id} value={String(r.id)}>
                        {r.full_name}
                      </option>
                    ))}
                </select>
              </div>

              <p className="text-sm text-muted-foreground">
                Date range: {dateFrom} to {dateTo}
              </p>

              <div className="flex justify-end gap-2">
                <DialogClose asChild>
                  <Button variant="outline">Cancel</Button>
                </DialogClose>
                <Button
                  disabled={!form.scope_id || runAnalysis.isPending}
                  onClick={() => {
                    runAnalysis.mutate(
                      {
                        ...form,
                        date_from: new Date(dateFrom).toISOString(),
                        date_to: new Date(dateTo).toISOString(),
                      },
                      { onSuccess: () => setOpen(false) }
                    )
                  }}
                >
                  {runAnalysis.isPending ? 'Running...' : 'Run Analysis'}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading...</div>
      ) : (history ?? []).length === 0 ? (
        <p className="text-muted-foreground">No analyses yet. Run one to get started.</p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Scope</TableHead>
                <TableHead>Date Range</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Tokens</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(history ?? []).map((a) => (
                <>
                  <TableRow
                    key={a.id}
                    className="cursor-pointer"
                    onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}
                  >
                    <TableCell>
                      <Badge variant="secondary">{a.analysis_type}</Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-muted-foreground">{a.scope_type}:</span>{' '}
                      {a.scope_id}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {a.date_from ? new Date(a.date_from).toLocaleDateString() : ''} -{' '}
                      {a.date_to ? new Date(a.date_to).toLocaleDateString() : ''}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{a.model_used}</TableCell>
                    <TableCell className="text-sm">{a.tokens_used ?? '-'}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(a.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                  {expandedId === a.id && (
                    <TableRow key={`${a.id}-detail`}>
                      <TableCell colSpan={6} className="bg-muted/30 p-0">
                        <div className="p-4">
                          {a.input_summary && (
                            <p className="mb-2 text-sm text-muted-foreground">
                              {a.input_summary}
                            </p>
                          )}
                          <pre className="max-h-80 overflow-auto rounded bg-muted p-3 text-xs">
                            {JSON.stringify(a.result, null, 2)}
                          </pre>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
