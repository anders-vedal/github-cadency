# Task P2-04: Display Approval Metrics in Frontend

## Phase
Phase 2 — Make It Smart

## Status
completed

## Blocked By
- P2-03-approved-at-merge-latency (completed)

## Blocks
None

## Description
Display the new approval latency metrics (P2-03) in the frontend. The backend now exposes `avg_time_to_approve_hours`, `avg_time_after_approve_hours`, and `prs_merged_without_approval` in `DeveloperStatsResponse`, plus `time_to_approve_h` and `time_after_approve_h` in benchmarks, and `merged_without_approval` workload alerts.

## Deliverables

### DeveloperDetail page
- [x] Add StatCards for:
  - "Avg Time to Approve" (hours) — with methodology tooltip: "Average time from PR creation to last approval review"
  - "Avg Time After Approve" (hours) — with methodology tooltip: "Average time from last approval to merge (post-approval idle time)"
  - "PRs Merged Without Approval" (count) — with methodology tooltip: "PRs merged without any APPROVED review"
- [x] For lower-is-better metrics, green delta = decrease

### Dashboard page
- [x] Show `prs_merged_without_approval` if > 0 in team status grid or as alert
- [x] Show `merged_without_approval` alerts from workload endpoint in the alert strip

### DeveloperDetail — Percentile bars
- [x] Add PercentileBar for `time_to_approve_h` and `time_after_approve_h` in the Team Context section (lower is better)

### TypeScript types
- [x] Add `avg_time_to_approve_hours`, `avg_time_after_approve_hours`, `prs_merged_without_approval` to `DeveloperStats` interface
- [x] Add `time_to_approve_h`, `time_after_approve_h` to benchmark metric names

## Files Modified
- `frontend/src/utils/types.ts` — Added approval fields to `DeveloperStats`, added `merged_without_approval` to `WorkloadAlert` type union
- `frontend/src/pages/DeveloperDetail.tsx` — Added 3 approval StatCards with tooltips, added `time_to_approve_h` and `time_after_approve_h` to percentileLabels
- `frontend/src/pages/Dashboard.tsx` — Added `merged_without_approval` to alert severity map (warning level)

## Notes
- Dashboard shows `merged_without_approval` via the workload alerts (both per-developer and team-level), rendered in the existing alert strip with warning severity. No separate team status grid column was needed since the workload endpoint already emits these alerts.
- PercentileBar keys use `time_to_approve_h` / `time_after_approve_h` to match backend benchmark/percentile key names.
