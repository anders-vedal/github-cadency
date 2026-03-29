import { TableHead } from '@/components/ui/table'

export default function SortableHead<T extends string>({
  field,
  current,
  asc,
  onToggle,
  children,
}: {
  field: T
  current: T
  asc: boolean
  onToggle: (f: T) => void
  children: React.ReactNode
}) {
  const active = field === current
  return (
    <TableHead>
      <button
        type="button"
        className="inline-flex items-center gap-1 hover:text-foreground"
        onClick={() => onToggle(field)}
      >
        {children}
        {active && (
          <span className="text-xs">{asc ? '\u2191' : '\u2193'}</span>
        )}
      </button>
    </TableHead>
  )
}
