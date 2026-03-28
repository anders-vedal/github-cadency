# Task M2: Team-Relative Context (Benchmarks)

## Phase
Management Phase 1 — Extends Phase 2 (stats)

## Status
completed

## Blocked By
- 07-stats-service

## Blocks
- M5-one-on-one-prep-brief
- M8-team-health-check

## Description
Add a team benchmarks endpoint that computes percentile bands (p25/p50/p75) across all active developers. Extend individual DeveloperStats responses with percentile placement. Corresponds to DEVPULSE_MANAGEMENT_FEATURES.md section M1.

## Deliverables

### backend/app/services/stats.py (extend)
**Benchmark computation:**
- Compute p25, p50, p75 percentiles for all active developers in a team for a given period
- Metrics: time_to_merge_h, time_to_first_review_h, prs_merged, review_turnaround_h, reviews_given, additions_per_pr
- Return sample_size (number of developers included)

**Developer percentile placement:**
- For each metric in DeveloperStats, compute which percentile band the developer falls in
- Bands: `below_p25`, `p25_to_p50`, `p50_to_p75`, `above_p75`
- Include `team_median` value for each metric

### backend/app/api/stats.py (extend)
**GET /api/stats/benchmarks**
- Query params: date_from, date_to, team (optional)
- Returns percentile bands for all metrics with sample_size
- Computed at query time from existing stats (no new tables)

**Extend GET /api/stats/developer/{id}**
- Add optional `include_percentiles=true` query param
- When enabled, response includes `percentiles` field with band placement and team median for each metric

### backend/app/schemas/ (extend)
- `BenchmarkMetric` schema: p25, p50, p75 values
- `BenchmarksResponse` schema: period, sample_size, metrics dict
- `PercentilePlacement` schema: value, percentile_band, team_median
- Extend `DeveloperStatsResponse` with optional percentiles field

### Frontend considerations (later)
Percentile bands render as colored indicators: green for "typical" (p25-p75), amber for "notable" (outside). No red. Context, not punishment.
