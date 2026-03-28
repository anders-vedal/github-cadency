# Task P1-05: Add Recharts and Trend Visualizations

## Phase
Phase 1 — Make It Usable

## Status
completed

## Blocked By
- M3-trend-lines
- 12-frontend-remaining-pages

## Blocks
- P1-02-actionable-dashboard

## Description
Add a charting library and build trend visualizations for the Developer Detail page. The backend already computes 8-period trend data with linear regression and direction classification (`GET /api/stats/developer/{id}/trends`) — none of it is visualized. This task also adds percentile placement bars using the existing `?include_percentiles=true` API parameter.

## Deliverables

### Install Recharts
```bash
cd frontend && pnpm add recharts
```

### frontend/src/hooks/useStats.ts (extend)
- Add `useDeveloperTrends(developerId, periodType, periods)` hook calling `GET /api/stats/developer/{id}/trends`
- Modify `useDeveloperStats` to pass `include_percentiles=true` by default

### frontend/src/utils/types.ts (extend)
- Add TypeScript interfaces: `DeveloperTrendsResponse`, `TrendPeriod`, `TrendDirection`, `PercentilePlacement`

### frontend/src/components/charts/ (new directory)

**TrendChart.tsx**
- Recharts `AreaChart` or `LineChart` component
- Props: `data: TrendPeriod[]`, `metricKey: string`, `direction: TrendDirection`
- X-axis: period labels (week start dates)
- Y-axis: metric value
- Regression trend line overlaid (dashed)
- Direction badge: "Improving" (green), "Stable" (gray), "Worsening" (red)

**PercentileBar.tsx**
- Horizontal bar showing where a developer sits relative to team p25/p50/p75
- Props: `value: number`, `p25: number`, `p50: number`, `p75: number`, `label: string`, `lowerIsBetter?: boolean`
- Color zones: below p25 (red/green depending on polarity), p25-p50 (amber), p50-p75 (light green), above p75 (green/red)
- Developer's position marked with a dot/line

**ReviewQualityDonut.tsx**
- Recharts `PieChart` showing review quality tier distribution
- Segments: thorough (green), standard (blue), minimal (amber), rubber_stamp (gray)
- Center text: quality score (0-10)

### frontend/src/pages/DeveloperDetail.tsx (extend)
Add three new sections below existing stat cards:

**"Your Trends" section:**
- Grid of 4-6 TrendChart components for key metrics: prs_merged, time_to_merge, reviews_given, review_quality_score, time_to_first_review
- Each chart shows the trend direction label from the API

**"Team Context" section:**
- Grid of PercentileBar components for each metric where percentile data is available
- Shows where this developer sits relative to team benchmarks

**"Review Quality" section:**
- ReviewQualityDonut showing tier distribution
- Below: list of recent reviews with tier badge and PR link

## Design Notes
- Charts should be responsive (use Recharts `ResponsiveContainer`)
- Use the existing shadcn/ui Card as wrapper for each chart
- Trend charts should respect the global date range from DateRangeContext
- Keep chart colors consistent with the rest of the UI (neutral base, accent for data)
