import { useMemo } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import type { ConversationsScatterPoint } from '@/utils/types'

interface CommentBounceScatterProps {
  points: ConversationsScatterPoint[]
}

interface RegressionResult {
  slope: number
  intercept: number
  r2: number
  line: { x: number; y: number }[]
}

function computeRegression(points: ConversationsScatterPoint[]): RegressionResult | null {
  const n = points.length
  if (n < 2) return null
  let sumX = 0
  let sumY = 0
  let sumXY = 0
  let sumX2 = 0
  for (const p of points) {
    sumX += p.comment_count
    sumY += p.review_rounds
    sumXY += p.comment_count * p.review_rounds
    sumX2 += p.comment_count * p.comment_count
  }
  const denom = n * sumX2 - sumX * sumX
  if (denom === 0) return null
  const slope = (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n

  const meanY = sumY / n
  let ssRes = 0
  let ssTot = 0
  for (const p of points) {
    const predicted = slope * p.comment_count + intercept
    ssRes += (p.review_rounds - predicted) ** 2
    ssTot += (p.review_rounds - meanY) ** 2
  }
  const r2 = ssTot === 0 ? 0 : 1 - ssRes / ssTot

  const xs = points.map((p) => p.comment_count)
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)
  const line = [
    { x: xMin, y: slope * xMin + intercept },
    { x: xMax, y: slope * xMax + intercept },
  ]

  return { slope, intercept, r2, line }
}

export default function CommentBounceScatter({ points }: CommentBounceScatterProps) {
  const regression = useMemo(() => computeRegression(points), [points])

  if (points.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No linked (issue, PR) pairs in this range.
      </p>
    )
  }

  const scatterData = points.map((p) => ({
    x: p.comment_count,
    y: p.review_rounds,
    issue: p.issue_identifier,
    pr: p.pr_number,
  }))

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {points.length} (issue, PR) pair{points.length === 1 ? '' : 's'}
        </span>
        {regression && (
          <span>
            R² = {regression.r2.toFixed(2)} &middot; slope ={' '}
            {regression.slope.toFixed(3)}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
          <XAxis
            type="number"
            dataKey="x"
            name="Comments"
            tick={{ fontSize: 12 }}
            label={{
              value: 'Comments per issue',
              position: 'insideBottom',
              offset: -5,
              fontSize: 11,
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Review rounds"
            tick={{ fontSize: 12 }}
            label={{
              value: 'PR review rounds',
              angle: -90,
              position: 'insideLeft',
              fontSize: 11,
            }}
          />
          <ZAxis type="number" range={[40, 40]} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              if (!active || !payload || payload.length === 0) return null
              const p = payload[0].payload as { x: number; y: number; issue: string; pr: number }
              return (
                <div className="rounded-md border bg-card px-2 py-1 text-xs shadow">
                  <div className="font-mono">{p.issue}</div>
                  <div className="text-muted-foreground">
                    PR #{p.pr} &middot; {p.x} comments &middot; {p.y} rounds
                  </div>
                </div>
              )
            }}
          />
          <Scatter data={scatterData} fill="hsl(var(--chart-1))" />
          {regression && (
            <Line
              data={regression.line}
              type="linear"
              dataKey="y"
              stroke="hsl(var(--chart-3))"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              legendType="none"
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
