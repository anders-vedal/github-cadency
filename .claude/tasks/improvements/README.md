# DevPulse Improvement Tasks

Generated from the [Deep Dive Analysis](../../docs/analysis/DEEP-DIVE-ANALYSIS.md) on 2026-03-28.

Tasks are organized into 4 phases. Each task is self-contained and can be cherry-picked independently, though dependencies are noted. Use `/task-planner` to launch any task.

## Phase 1: "Make It Usable" (Frontend + Existing Data)

| Task | Title | Dependencies | Effort | Status |
|------|-------|-------------|--------|--------|
| [P1-01](P1-01-developer-self-access.md) | Developer Self-Access Tokens | — | Medium | **Done** |
| [P1-02](P1-02-actionable-dashboard.md) | Actionable Dashboard (Alerts + Grid + Deltas) | P1-05 | Medium | **Done** |
| [P1-03](P1-03-developer-self-goals.md) | Developer Self-Goal Creation | P1-01 | Small | **Done** |
| [P1-04](P1-04-structured-ai-rendering.md) | Structured AI Result Rendering | — | Medium | **Done** |
| [P1-05](P1-05-recharts-trend-viz.md) | Recharts + Trend Visualizations | — | Medium | **Done** |
| [P1-06](P1-06-frontend-polish.md) | Frontend Polish (Errors, Toasts, Skeletons) | — | Medium | **Done** |
| [P1-07](P1-07-draft-pr-filtering.md) | Draft PR Filtering + Workload Fix | — | Small | **Done** |
| [P1-08](P1-08-methodology-tooltips.md) | Methodology Tooltips | — | Small | **Done** |
| [P1-09](P1-09-sync-page-ux.md) | Sync Page UX (Repos, Progress, Scope) | — | Medium | |

## Phase 2: "Make It Smart" (New Computations from Existing Data)

| Task | Title | Dependencies | Effort | Status |
|------|-------|-------------|--------|--------|
| [P2-01](P2-01-stale-pr-endpoint.md) | Stale PR List Endpoint | P1-07 | Medium | **Done** |
| [P2-02](P2-02-review-round-trips.md) | Review Round-Trip Count | — | Small | **Done** |
| [P2-03](P2-03-approved-at-merge-latency.md) | Approved-At + Post-Approval Merge Latency | — | Small | **Done** |
| [P2-04](P2-04-issue-pr-linkage.md) | Issue-to-PR Linkage (Closing Keywords) | — | Medium | **Done** |
| [P2-05](P2-05-pr-metadata-capture.md) | Capture PR Labels, Merged-By, Branches | — | Small | **Done** |
| [P2-06](P2-06-revert-detection.md) | Revert PR Detection | P2-05 | Small | **Done** |
| [P2-07](P2-07-review-quality-algorithm-fix.md) | Fix Review Quality Algorithm | — | Small | **Done** |
| [P2-08](P2-08-workload-collaboration-pages.md) | Workload + Collaboration + Benchmarks Pages | P1-05 | Large | **Done** |
| [P2-09](P2-09-goals-page.md) | Goals Management Page | P1-05 | Medium | **Done** |

## Phase 3: "Make It Proactive" (New Integrations + Novel Features)

| Task | Title | Dependencies | Effort | Status |
|------|-------|-------------|--------|--------|
| [P3-01](P3-01-slack-webhook-notifications.md) | Slack Webhook Notifications | P2-01 | Medium | |
| [P3-02](P3-02-sprint-model.md) | Sprint Model + Planned vs Actual | — | Medium | |
| [P3-03](P3-03-issue-quality-scoring.md) | Issue Quality Scoring | P2-04 | Medium | **Done** |
| [P3-04](P3-04-issue-creator-analytics.md) | Issue Creator Analytics (Mgmt Friction) | P3-03 | Medium | **Done** |
| [P3-05](P3-05-pr-risk-scoring.md) | PR Risk Scoring | P2-05, P2-02 | Medium | **Done** |
| [P3-06](P3-06-code-churn-analysis.md) | Code Churn Analysis (File-Level) | — | Large | **Done** |
| [P3-07](P3-07-ci-check-runs.md) | CI/CD Check-Run Integration | — | Large | **Done** |
| [P3-08](P3-08-quarterly-report-export.md) | Quarterly Performance Report Export | — | Medium | |
| [P3-09](P3-09-configurable-alert-thresholds.md) | Configurable Alert Thresholds | P3-01 | Small | |
| [P3-10](P3-10-developer-work-notes.md) | Developer "Invisible Work" Notes | P1-01 | Small | |

## Phase 4: "Make It Best-in-Class" (Competitive Differentiators)

| Task | Title | Dependencies | Effort | Status |
|------|-------|-------------|--------|--------|
| [P4-01](P4-01-dora-metrics.md) | DORA Metrics (Deploy Frequency + Lead Time) | P3-07 | Large | **Done** |
| [P4-02](P4-02-work-categorization.md) | Work Categorization (Feature/Bug/Debt/Ops) | P2-05, P3-03 | Medium | **Done** |
| [P4-03](P4-03-review-comment-categorization.md) | Review Comment Categorization | — | Medium | **Done** |
| [P4-04](P4-04-executive-dashboard.md) | Executive Reporting Dashboard | P1-05, P2-08 | Large | **Done** |
| [P4-05](P4-05-bulk-one-on-one-prep.md) | Bulk 1:1 Prep Generation | P1-04 | Medium | |

## Phase 5: "Operational Excellence" (Admin Controls & Cost Management)

| Task | Title | Dependencies | Effort | Status |
|------|-------|-------------|--------|--------|
| [P5-01](P5-01-ai-settings-backend.md) | AI Settings & Cost Controls — Backend | — | Large | **Done** |
| [P5-02](P5-02-ai-usage-tracking.md) | AI Usage Tracking & Cost Estimation API | P5-01 | Medium | **Done** |
| [P5-03](P5-03-ai-settings-frontend.md) | AI Settings & Cost Controls — Frontend | P5-01, P5-02 | Large | **Done** |

## Quick Start Recommendations

**If you want maximum user impact with minimum effort, start with these (no dependencies):**
1. P1-07 — Draft PR Filtering (small, fixes misleading data)
2. P2-07 — Fix Review Quality Algorithm (small, fixes unfair metrics)
3. P2-05 — Capture PR Metadata (small, unlocks many downstream features)
4. P1-06 — Frontend Polish (medium, makes the app feel professional)
5. P1-05 — Recharts + Trends (medium, makes existing data visible)

**The single highest-impact task:** P1-02 (Actionable Dashboard) — transforms DevPulse from a wall of numbers into a daily tool. Depends on P1-05.
