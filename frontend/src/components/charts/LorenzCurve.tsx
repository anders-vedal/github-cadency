import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

interface LorenzCurveProps {
  /** Raw values — e.g., review counts per reviewer. Order doesn't matter. */
  values: number[]
  gini?: number
  height?: number
}

/**
 * Computes the Lorenz curve from a list of non-negative values.
 *
 * Returns an array of (x, y) pairs where x is cumulative share of population
 * (0..1) and y is cumulative share of the resource (0..1).
 */
function computeLorenz(values: number[]): { x: number; y: number; equality: number }[] {
  if (values.length === 0) return [{ x: 0, y: 0, equality: 0 }, { x: 1, y: 1, equality: 1 }]
  const sorted = [...values].sort((a, b) => a - b)
  const total = sorted.reduce((s, v) => s + v, 0)
  if (total === 0) return [{ x: 0, y: 0, equality: 0 }, { x: 1, y: 1, equality: 1 }]
  const points: { x: number; y: number; equality: number }[] = [{ x: 0, y: 0, equality: 0 }]
  let cum = 0
  for (let i = 0; i < sorted.length; i++) {
    cum += sorted[i]
    const x = (i + 1) / sorted.length
    const y = cum / total
    points.push({ x, y, equality: x })
  }
  return points
}

export default function LorenzCurve({ values, gini, height = 260 }: LorenzCurveProps) {
  const data = useMemo(() => computeLorenz(values), [values])

  return (
    <div className="space-y-2">
      {gini != null && (
        <div className="text-xs text-muted-foreground">
          Gini coefficient: <span className="font-semibold text-foreground">{gini.toFixed(3)}</span>
          {' '}(0 = perfect equality, 1 = one reviewer does everything)
        </div>
      )}
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            type="number"
            dataKey="x"
            domain={[0, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            tick={{ fontSize: 11 }}
            label={{
              value: 'Cumulative share of reviewers',
              position: 'insideBottom',
              offset: -5,
              fontSize: 11,
            }}
          />
          <YAxis
            type="number"
            domain={[0, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            tick={{ fontSize: 11 }}
            label={{
              value: 'Cumulative share of reviews',
              angle: -90,
              position: 'insideLeft',
              fontSize: 11,
            }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload || payload.length === 0) return null
              const row = payload[0].payload as { x: number; y: number }
              return (
                <div className="rounded-md border bg-card px-2 py-1 text-xs shadow">
                  <div>Bottom {Math.round(row.x * 100)}% of reviewers</div>
                  <div className="text-muted-foreground">
                    did {Math.round(row.y * 100)}% of reviews
                  </div>
                </div>
              )
            }}
          />
          <Line
            type="monotone"
            dataKey="equality"
            stroke="hsl(var(--muted-foreground))"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            legendType="none"
          />
          <Area
            type="monotone"
            dataKey="y"
            stroke="hsl(var(--chart-1))"
            fill="hsl(var(--chart-1))"
            fillOpacity={0.2}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
