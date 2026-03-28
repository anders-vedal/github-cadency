import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDevelopers, useCreateDeveloper, useUpdateDeveloper } from '@/hooks/useDevelopers'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { Developer, DeveloperCreate } from '@/utils/types'

const ROLES = ['developer', 'senior_developer', 'lead', 'architect', 'devops', 'qa', 'intern']

function DeveloperForm({
  initial,
  onSubmit,
  submitLabel,
}: {
  initial?: Partial<DeveloperCreate>
  onSubmit: (data: DeveloperCreate) => void
  submitLabel: string
}) {
  const [form, setForm] = useState<DeveloperCreate>({
    github_username: initial?.github_username ?? '',
    display_name: initial?.display_name ?? '',
    email: initial?.email ?? '',
    role: initial?.role ?? '',
    team: initial?.team ?? '',
    skills: initial?.skills ?? [],
    specialty: initial?.specialty ?? '',
    location: initial?.location ?? '',
    timezone: initial?.timezone ?? '',
  })

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(form)
      }}
    >
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="github_username">GitHub Username *</Label>
          <Input
            id="github_username"
            value={form.github_username}
            onChange={(e) => setForm({ ...form, github_username: e.target.value })}
            required
            disabled={!!initial?.github_username}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="display_name">Display Name *</Label>
          <Input
            id="display_name"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={form.email ?? ''}
            onChange={(e) => setForm({ ...form, email: e.target.value || null })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="role">Role</Label>
          <select
            id="role"
            className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm"
            value={form.role ?? ''}
            onChange={(e) => setForm({ ...form, role: e.target.value || null })}
          >
            <option value="">Select role...</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>{r.replace('_', ' ')}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="team">Team</Label>
          <Input
            id="team"
            value={form.team ?? ''}
            onChange={(e) => setForm({ ...form, team: e.target.value || null })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="skills">Skills (comma-separated)</Label>
          <Input
            id="skills"
            value={(form.skills ?? []).join(', ')}
            onChange={(e) =>
              setForm({
                ...form,
                skills: e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="location">Location</Label>
          <Input
            id="location"
            value={form.location ?? ''}
            onChange={(e) => setForm({ ...form, location: e.target.value || null })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="timezone">Timezone</Label>
          <Input
            id="timezone"
            placeholder="e.g. Europe/Oslo"
            value={form.timezone ?? ''}
            onChange={(e) => setForm({ ...form, timezone: e.target.value || null })}
          />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <DialogClose asChild>
          <Button variant="outline">Cancel</Button>
        </DialogClose>
        <Button type="submit">{submitLabel}</Button>
      </div>
    </form>
  )
}

export default function TeamRegistry() {
  const navigate = useNavigate()
  const [teamFilter, setTeamFilter] = useState('')
  const { data: developers, isLoading } = useDevelopers(teamFilter || undefined)
  const createDev = useCreateDeveloper()
  const [editDev, setEditDev] = useState<Developer | null>(null)
  const updateDev = useUpdateDeveloper(editDev?.id ?? 0)
  const [addOpen, setAddOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)

  const teams = [...new Set((developers ?? []).map((d) => d.team).filter(Boolean))] as string[]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Team Registry</h1>
        <div className="flex items-center gap-3">
          <select
            className="rounded-md border bg-background px-3 py-1.5 text-sm"
            value={teamFilter}
            onChange={(e) => setTeamFilter(e.target.value)}
          >
            <option value="">All teams</option>
            {teams.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          <Dialog open={addOpen} onOpenChange={setAddOpen}>
            <DialogTrigger asChild>
              <Button>Add Developer</Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>Add Developer</DialogTitle>
              </DialogHeader>
              <DeveloperForm
                submitLabel="Create"
                onSubmit={(data) => {
                  createDev.mutate(data, { onSuccess: () => setAddOpen(false) })
                }}
              />
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading...</div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>GitHub</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Team</TableHead>
                <TableHead>Skills</TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Timezone</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(developers ?? []).map((dev) => (
                <TableRow
                  key={dev.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/team/${dev.id}`)}
                >
                  <TableCell className="font-medium">{dev.display_name}</TableCell>
                  <TableCell className="text-muted-foreground">{dev.github_username}</TableCell>
                  <TableCell>
                    {dev.role && (
                      <Badge variant="secondary">{dev.role.replace('_', ' ')}</Badge>
                    )}
                  </TableCell>
                  <TableCell>{dev.team}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {(dev.skills ?? []).slice(0, 3).map((s) => (
                        <Badge key={s} variant="outline" className="text-xs">{s}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{dev.location}</TableCell>
                  <TableCell className="text-muted-foreground">{dev.timezone}</TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditDev(dev)
                        setEditOpen(true)
                      }}
                    >
                      Edit
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {(developers ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="text-center text-muted-foreground">
                    No developers found. Add one to get started.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit Developer</DialogTitle>
          </DialogHeader>
          {editDev && (
            <DeveloperForm
              initial={editDev}
              submitLabel="Save"
              onSubmit={({ github_username, ...updateData }) => {
                void github_username
                updateDev.mutate(updateData, { onSuccess: () => setEditOpen(false) })
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
