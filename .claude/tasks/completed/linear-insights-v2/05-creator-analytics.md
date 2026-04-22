# Phase 05: Creator analytics on Developer Detail

**Status:** Completed (2026-04-22)
**Priority:** Medium
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/app/services/developer_linear.py` — `get_developer_creator_profile`,
  `get_developer_worker_profile`, `get_developer_shepherd_profile`
- `frontend/src/components/developer/LinearCreatorSection.tsx`
- `frontend/src/components/developer/LinearWorkerSection.tsx`
- `frontend/src/components/developer/LinearShepherdSection.tsx`
- `frontend/src/hooks/useDeveloperLinear.ts` (3 hooks with `enabled: hasLinear && isPrimary`)

## Files Modified
- `backend/app/api/developers.py` — `GET /api/developers/{id}/linear-creator-profile`,
  `/linear-worker-profile`, `/linear-shepherd-profile` with `_assert_self_or_admin()` gate
- `backend/app/schemas/schemas.py` — `LinearCreatorProfile`, `LinearWorkerProfile`,
  `LinearShepherdProfile`, `LabelCountRow`, `ShepherdCollaborator`
- `frontend/src/pages/DeveloperDetail.tsx` — inserted 3 stacked `<h2>` sections after Active
  Sprint Card; Creator + Shepherd gated on `isAdmin || isOwnPage`, Worker visible on detail page
- `frontend/src/utils/types.ts`

## Deviations from spec
- `StatCard.pairedOutcome` slot (Phase 11) not added — Ticket Clarity stat serves as
  implicit outcome pairing via sample-size badging

## Blocked By
- 01-sync-depth-foundations
- 02-linking-upgrade-and-quality

## Blocks
- None

## Description

Augment the Developer Detail page with three new stacked `<h2>` sections ("Linear creator",
"Linear worker", "Linear shepherd") showing each developer both as a creator (tickets they
write), worker (tickets they execute), and shepherd (comments on others' issues).

## Research-driven adjustments

- **DeveloperDetail has NO tab system.** The page is a single vertical `space-y-6` scroll with
  sections separated by `<h2 className="text-lg font-semibold">` headings. Earlier plan said
  "new tab" — that was wrong. Insert three new sections in the existing vertical flow, same
  pattern as the Active Sprint Card already does (see `DeveloperDetail.tsx:533`).
- **`get_issue_creator_stats` already exists** at `stats.py:3025` with a Linear branch at
  `_get_issue_creator_stats_linear` (3172). This phase **extends** that function, doesn't
  create a parallel one. The extension adds downstream-PR review-round-count correlation
  (which requires the Phase 02 linker upgrade).
- **`_compute_per_developer_metrics`** at `stats.py:1051` is the batch benchmark engine. New
  creator metrics get emitted from that function (not from a parallel pipeline) so they
  participate in benchmarking automatically.
- **Visibility gating** — per Phase 11 (Metrics Governance), creator-outcome correlation is
  `self + admin` visibility by default. The new sections hide on a developer's page unless the
  viewer is that developer or an admin. This is enforced at the API layer, not just UI.

## Deliverables

### backend/app/services/stats.py — extend, don't duplicate

- **Extend** `_get_issue_creator_stats_linear` (stats.py:3172) with new fields:
  `avg_downstream_pr_review_rounds` and `sample_size_downstream_prs`. Join
  `PRExternalIssueLink` → `PullRequest.review_round_count` and average.
- **Extend** `_compute_per_developer_metrics` (stats.py:1051) with the new creator metrics so
  they participate in benchmarking automatically.
- New thin functions in `services/developer_linear.py` for the worker/shepherd profiles that
  aren't already covered — these wrap existing history queries:

- `get_developer_creator_profile(db, developer_id, since, until)` →
  ```python
  {
      "issues_created": int,
      "issues_created_by_type": {"bug": int, "feature": int, "tech_debt": int, ...},
      "top_labels": [{"label": str, "count": int}],
      "avg_description_length": int,
      "avg_comments_generated": float,        # avg comments on their issues (exc. system)
      "avg_downstream_pr_review_rounds": float,  # ticket clarity signal
      "sample_size_downstream_prs": int,
      "self_assigned_pct": float,             # of their created issues
      "median_time_to_close_for_their_issues_s": int | None,
  }
  ```

- `get_developer_worker_profile(db, developer_id, since, until)` →
  ```python
  {
      "issues_worked": int,
      "self_picked_count": int,               # where creator == developer
      "pushed_count": int,
      "self_picked_pct": float,
      "median_triage_to_start_s": int,
      "median_cycle_time_s": int,
      "issues_worked_by_status": {"todo": int, "in_progress": int, "done": int},
      "reassigned_to_other_count": int,       # issues handed off mid-flight (from history)
  }
  ```

- `get_developer_shepherd_profile(db, developer_id, since, until)` →
  ```python
  {
      "comments_on_others_issues": int,
      "issues_commented_on": int,
      "unique_teams_commented_on": int,       # derived from project/cycle team_key
      "is_shepherd": bool,                    # >3x team median = True
      "top_collaborators": [                  # people whose issues this dev comments on most
          {"developer_id": int, "name": str, "count": int}
      ],
  }
  ```

- All three functions respect existing contribution-category rules — system accounts skipped

### backend/app/api/developers.py

- `GET /api/developers/{id}/linear-creator-profile?since=&until=`
- `GET /api/developers/{id}/linear-worker-profile?since=&until=`
- `GET /api/developers/{id}/linear-shepherd-profile?since=&until=`
- All require the caller to either be admin OR be viewing their own developer page (existing pattern)

### backend/app/schemas/schemas.py

- `LinearCreatorProfile`, `LinearWorkerProfile`, `LinearShepherdProfile`

### frontend/src/pages/DeveloperDetail.tsx

- Insert three new stacked sections (not tabs) in the existing vertical flow, placed after
  the Active Sprint Card (around line 568) and before the stats grid. Each section follows
  the existing pattern: `<div className="space-y-3"><h2 className="text-lg font-semibold">` + card
  or grid
- Sections only render when `hasLinear && isPrimary` (use `useIntegrations()` per the
  no-IntegrationsContext pattern)
- Creator and Shepherd sections only render when viewer is self or admin (visibility gate per
  Phase 11)

### frontend/src/components/developer/ (new components)

1. **`LinearCreatorSection.tsx`** — stat grid (issues written, avg description length, avg
   dialogue generated, ticket-clarity signal) + top labels chip cloud + a small bar chart of
   downstream PR bounce distribution. Uses existing `StatCard` pattern with `pairedOutcome` slot
   (per Phase 11: activity metrics always paired with outcome).
2. **`LinearWorkerSection.tsx`** — stat grid (issues executed, self-picked %, median
   triage-to-start, median cycle time) + a bar chart splitting issues by status. Use
   `DistributionStatCard` (Phase 11) for cycle time.
3. **`LinearShepherdSection.tsx`** — stat grid (comments on others' issues, unique
   collaborators) + top-collaborators table with a visual network mini-graph (future
   nice-to-have; v1 a flat table).

Framing copy is critical: creator profile must feel like "how clear are my tickets", not a score.
Shepherd framing: "which collaborators do you engage with most, and across which teams?"

### frontend/src/hooks/

- `useDeveloperLinearCreator(developerId, dateRange)`
- `useDeveloperLinearWorker(developerId, dateRange)`
- `useDeveloperLinearShepherd(developerId, dateRange)`

### Tests

- `backend/tests/services/test_developer_linear.py`: creator signal, worker signal, shepherd
  threshold (3x team median) against seeded data
- E2E test that opens a developer page, switches to Linear patterns tab, and verifies the three
  sub-sections render with expected values

## Acceptance criteria

- [x] Creator profile aggregates issues written and computes downstream PR review-round-count
      correctly
- [x] Worker profile correctly separates self-picked from pushed issues using history
- [x] Shepherd profile identifies developers commenting on others' issues at > 3x the team median
- [x] Sections only render when Linear is primary (stacked `<h2>` sections, not tabs)
- [x] Empty state (new developer, no Linear activity) is handled gracefully
- [ ] Copy framing approved by product — creator signal not presented as a ranking (pending review)
