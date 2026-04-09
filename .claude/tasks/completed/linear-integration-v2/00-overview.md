# Linear Integration v2 — Overview

> Priority: High | Effort: Large | Impact: High
> Prerequisite: Phase 1 complete (backend data layer + frontend pages exist)
> Related: `.claude/tasks/linear-integration/01-linear-integration.md`
> **Status: All phases completed (2026-04-07)**

## Problem Statement

The Linear integration syncs data (projects, cycles, issues) and has 3 dedicated frontend pages (Sprints, Planning, Projects). But the data is siloed — the entire rest of DevPulse (stats, benchmarks, notifications, AI, collaboration, work categories) queries only GitHub `issues`. The `is_primary_issue_source` toggle exists in the DB and UI but no service ever calls `get_primary_issue_source()` to branch behavior.

For teams using Linear as their primary issue tracker, the core DevPulse experience — DeveloperDetail stats, benchmarks, workload, AI analysis — completely ignores their issue data.

## Goal

Make the Linear integration a first-class citizen: when a team toggles Linear as primary, their issue data flows through every feature that currently uses GitHub issues. Fix existing bugs. Add sprint-aware notifications and AI context. Make the sync robust.

## State Before v2 (as of 2026-04-06)

**What works:**
- Linear GraphQL client (read-only, projects/cycles/issues sync)
- PR-to-issue linking via regex (`[A-Z]{2,10}-\d+` in title/branch/body)
- Developer auto-mapping by email
- Sprint stats service (velocity, completion, scope creep, triage, estimation, alignment, correlation)
- 3 frontend pages (SprintDashboard, PlanningInsights, ProjectPortfolio)
- Integration settings page (setup, test, sync, user mapping)
- 11 integration API endpoints + 12 sprint/planning API endpoints

**What's broken:**
- `get_primary_issue_source()` never called by `stats.py` or any other service
- Auto-mapped developers have `external_user_id=""` (empty string, not real ID)
- Potential route collision: `GET /integrations/issue-source` vs `GET /integrations/{id}/status`
- No concurrency guard on Linear sync (scheduler + manual can overlap)
- PR linking is full table scan on every sync
- `planned_scope` mixes Linear points and issue counts
- `ExternalSprint.url` never populated
- Sync interval not live-configurable

**What's missing:**
- Primary issue source branching in stats, benchmarks, notifications, AI, collaboration
- Sprint-aware notification alerts
- Linear data in AI analysis context
- Collaboration scoring from Linear issue co-assignment
- Workload enrichment from Linear sprint issues
- Work categorization for Linear issues
- Sync robustness (concurrency, cancellation, incremental linking)

## Phase Structure

| Phase | Task File | Focus | Effort | Status |
|-------|-----------|-------|--------|--------|
| 1 | `01-bugfixes.md` | Fix existing bugs and technical debt | Small | Completed |
| 2 | `02-primary-issue-source.md` | Make the toggle actually work in stats/benchmarks/linkage | Large | Completed |
| 3 | `03-ai-context-enrichment.md` | Feed Linear data into AI 1:1 prep and team health | Medium | Completed |
| 4 | `04-sprint-notifications.md` | Sprint-aware alert types in notification center | Medium | Completed |
| 5 | `05-collaboration-workload.md` | Linear data in collaboration scoring + workload | Medium | Completed |
| 6 | `06-sync-robustness.md` | Concurrency guard, incremental linking, cancellation, live config | Medium | Completed |
| 7 | `07-cross-linking-ux.md` | Sprint on DeveloperDetail, project health in dashboard | Medium | Completed |

Phases 1-2 are sequential (bugs first, then branching). Phases 3-5 are independent and can be parallelized. Phase 6 can run anytime. Phase 7 depends on phases 2-5 being complete.

## Key Files

| File | Role |
|------|------|
| `backend/app/services/linear_sync.py` | Sync client, orchestration, PR linking, dev mapping, `get_primary_issue_source()` |
| `backend/app/services/sprint_stats.py` | Sprint/planning metric computations |
| `backend/app/services/stats.py` | All GitHub-only issue metrics (THE gap) |
| `backend/app/services/ai_analysis.py` | AI context builders (no Linear data) |
| `backend/app/services/notifications.py` | 16 alert evaluators (all GitHub-only) |
| `backend/app/services/enhanced_collaboration.py` | Collaboration scoring (GitHub-only co-assignment) |
| `backend/app/services/work_category.py` | Work allocation (GitHub-only) |
| `backend/app/services/work_categories.py` | Classification rules (no Linear awareness) |
| `backend/app/api/integrations.py` | Integration config CRUD |
| `backend/app/api/sprints.py` | Sprint/planning data API |
| `backend/app/models/models.py` | ORM models (lines ~956-1146 for Linear tables) |
| `backend/app/schemas/schemas.py` | Pydantic schemas (lines ~1601-1844 for Linear) |
| `frontend/src/pages/insights/SprintDashboard.tsx` | Velocity/completion/scope charts |
| `frontend/src/pages/insights/PlanningInsights.tsx` | Triage/alignment/accuracy/correlation |
| `frontend/src/pages/insights/ProjectPortfolio.tsx` | Project health cards |
| `frontend/src/pages/settings/IntegrationSettings.tsx` | Admin setup UI |
