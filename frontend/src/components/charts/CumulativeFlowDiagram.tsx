import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { CumulativeFlowPoint } from '@/utils/types'

interface CumulativeFlowDiagramProps {
  data: CumulativeFlowPoint[]
  height?: number
}

const BANDS: { key: keyof CumulativeFlowPoint; label: string; color: string }[] = [
  { key: 'done', label: 'Done', color: 'hsl(var(--chart-1))' },
  { key: 'in_review', label: 'In Review', color: 'hsl(var(--chart-2))' },
  { key: 'in_progress', label: 'In Progress', color: 'hsl(var(--chart-3))' },
  { key: 'todo', label: 'Todo', color: 'hsl(var(--chart-4))' },
  { key: 'backlog', label: 'Backlog', color: 'hsl(var(--chart-5))' },
  { key: 'triage', label: 'Triage', color: '#94a3b8' },
  { key: 'cancelled', label: 'Cancelled', color: '#cbd5e1' },
]

export default function CumulativeFlowDiagram({ data, height = 320 }: CumulativeFlowDiagramProps) {
  if (data.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No flow data in this range.
      </p>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11 }}
          tickFormatter={(v: string) => v.slice(5)}
        />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '6px',
            fontSize: '12px',
          }}
        />
        <Legend wrapperStyle={{ fontSize: '11px' }} />
        {BANDS.map((band) => (
          <Area
            key={band.key as string}
            type="monotone"
            dataKey={band.key as string}
            name={band.label}
            stackId="flow"
            stroke={band.color}
            fill={band.color}
            fillOpacity={0.6}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}
