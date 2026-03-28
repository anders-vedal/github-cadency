# Task M3: Trend Lines

## Phase
Management Phase 1 — Extends Phase 2 (stats)

## Status
completed

## Blocked By
- 07-stats-service

## Blocks
- M5-one-on-one-prep-brief

## Description
Add a trends endpoint that returns developer stats bucketed by time period with linear regression trend analysis. Corresponds to DEVPULSE_MANAGEMENT_FEATURES.md section M2.

## Deliverables

### backend/app/services/stats.py (extend)
**Period bucketing:**
- Compute developer stats for each time bucket (week, sprint, or month)
- Return array of period objects with: start, end, prs_merged, avg_time_to_merge_h, reviews_given, additions, deletions, issues_closed

**Trend calculation via linear regression:**
- Fit linear regression over period buckets for each metric
- Classify direction as `improving`, `stable`, or `worsening` based on slope magnitude
- Include `change_pct` showing percentage change over the period range

**Metric polarity map (hardcoded):**
- Lower is better: time_to_merge_h, time_to_first_review_h, time_to_close_issue_h
- Higher is better: prs_merged, reviews_given, issues_closed
- Neutral (no direction judgment): additions, deletions, changed_files

Direction label must respect polarity — e.g., decreasing time_to_merge is "improving".

### backend/app/api/stats.py (extend)
**GET /api/stats/developer/{id}/trends**
- Query params:
  - `periods`: number of buckets (default: 8)
  - `period_type`: week | sprint | month (default: week)
  - `sprint_length_days`: only for period_type=sprint (default: 14)
- Returns developer_id, period_type, periods array, trends summary
- 404 if developer not found

### backend/app/schemas/ (extend)
- `TrendPeriod` schema: start, end, metric values
- `TrendDirection` schema: direction (improving/stable/worsening), change_pct
- `DeveloperTrendsResponse` schema: developer_id, period_type, periods list, trends dict

### Frontend considerations (later)
Render trends as sparklines on developer detail page. Color-code direction subtly.
