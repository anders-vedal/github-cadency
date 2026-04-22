# Phase 08: Performance follow-ups

**Status:** completed
**Priority:** Low
**Type:** performance
**Apps:** devpulse
**Effort:** small
**Parent:** linear-insights-v2-fixes/00-overview.md

## Blocked By
- None

## Blocks
- None

## Description

Four performance patterns surfaced in the review. None are correctness bugs; all will matter
as data scale grows. Priority is low — opportunistic fix, no rush. Do these when either (a)
profiling surfaces them, or (b) a developer is already in the file for another reason.

## Deliverables

### `backend/app/services/linear_sync.py` — scope existing-links preload

**Issue** (lines 1908-1911): `link_prs_to_external_issues` does
`select(PRExternalIssueLink)` with no filter, loading every row in the table into an
`existing_by_pair` dict. As the link table grows, this is a full-table scan loaded to memory
on every sync run. Also relevant for the admin-triggered `run_linear_relink()` path.

**Fix**: scope the preload to the issues touched in the current sync batch. The linker
already knows the set of issue IDs it's processing — add a `WHERE issue_id IN (...)` filter.
For the relink path which covers all issues, chunk the processing (e.g., 500 issues per
batch) and preload per-batch.

### `backend/app/services/bottleneck_intelligence.py` — batch-load in WIP + cross-team handoffs

**Issue**: `get_wip_per_developer` (lines 147-170) does `db.get(Developer, dev_id)` per
over-limit developer inside a loop. `get_cross_team_handoffs` (lines 310-326) does
`db.get(ExternalSprint, ...)` and `db.get(ExternalIssue, ...)` for every result row. O(N)
round trips.

**Fix**: mirror the pattern used elsewhere in the codebase. Collect IDs from the aggregate
query, batch-load via `select(Developer).where(Developer.id.in_(ids))` into a dict, then
enrich in Python. Same for the sprint + issue lookups in cross-team handoffs.

### `backend/app/services/dora_v2.py` — rework-rate join memory bound

**Issue** (lines 112-118): the self-join emits distinct `(base_id, base_merged_at,
followup_merged_at)` triples. The comment acknowledges "scales with number of file-overlap
pairs (small)" which holds until a repo has many shared filenames (`package.json`,
`README.md`, `pnpm-lock.yaml`). At that point the triples explode.

**Fix**: add a pre-filter at the SQL level on file popularity — exclude files touched by more
than some threshold (e.g., 20) of PRs in the window, since those files are effectively "every
PR touches this" and their overlap signal is noise. Document the threshold and make it a
constant at the top of the file. Alternative: compute the rework rate per-repo and aggregate,
reducing the cartesian blast radius.

### `backend/app/services/linkage_quality.py` — trend computation

**Issue**: `get_linkage_rate_trend` walks weekly windows, each issuing its own count query.
For the 12-week default that's 24 queries per request.

**Fix**: single query with `date_trunc('week', ...)` grouping, then Python-side padding for
weeks with zero PRs. Falls back to per-week queries in SQLite (test DB) if `date_trunc`
isn't available — or use a portable CASE expression.

## Acceptance criteria

- [x] `link_prs_to_external_issues` preload is scoped to this integration's issue ids
      (previously selected every `PRExternalIssueLink` row in the DB)
- [ ] `get_wip_per_developer` and `get_cross_team_handoffs` batch-loads — **deferred**,
      see note below
- [x] `compute_rework_rate` has a documented filename-popularity threshold
      (`_REWORK_FILE_POPULARITY_THRESHOLD = 20`) that excludes "everyone touches it"
      files (package.json, lock files, i18n catalogs) from the rework self-join
- [x] `get_linkage_rate_trend` confirmed to use 2 queries total regardless of week count
      (the original spec claim of 24 queries was inaccurate; the implementation already
      batched). Kept the comment alignment update.
- [ ] Before/after query count documentation — **deferred** (pairs with the
      `bottleneck_intelligence` batch-load work below)

## Deferrals

- **Bottleneck-intelligence batch-load**: the N+1 is real but localized to the admin
  Bottlenecks page, and this phase is tagged Priority: Low. Fixing it cleanly requires
  threading a developer-id-set through multiple helpers and adding regression tests.
  Deferred to a follow-up so it can ship with a query-count assertion rather than
  landing quietly.

## Files Modified

- `backend/app/services/linear_sync.py` — scoped `existing_by_pair` preload
- `backend/app/services/dora_v2.py` — filename-popularity threshold constant + subquery
- `backend/app/services/linkage_quality.py` — comment alignment
