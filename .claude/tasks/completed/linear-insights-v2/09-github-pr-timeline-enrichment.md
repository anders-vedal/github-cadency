# Phase 09: GitHub PR timeline enrichment

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** large
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/migrations/versions/043_github_pr_timeline.py` (revision 043 ← 042)
- `backend/app/services/github_timeline.py` — `TIMELINE_QUERY`, `fetch_pr_timeline_batch`,
  `persist_timeline_events`, `derive_pr_aggregates`
- `backend/app/services/pr_cycle_stages.py` — `compute_pr_stage_durations`,
  `get_pr_cycle_stage_distribution`
- `backend/app/services/codeowners.py` — `parse_codeowners`, `matching_owners`, `check_bypass`
- `backend/tests/unit/test_codeowners.py` (21 tests)
- `backend/tests/unit/test_pr_cycle_stages.py` (12 tests)
- `backend/tests/integration/test_github_timeline_sync.py` (12 tests)

## Files Modified
- `backend/app/models/models.py` — new `PRTimelineEvent` model + extended `PullRequest` with
  9 new columns: `force_push_count_after_first_review`, `review_requested_count`,
  `ready_for_review_at`, `draft_flip_count`, `renamed_title_count`,
  `dismissed_review_count`, `merge_queue_waited_s`, `auto_merge_waited_s`, `codeowners_bypass`
- `backend/app/services/notifications.py` — 4 new alert types: `pr_review_ping_pong`,
  `pr_force_push_after_review`, `codeowners_bypassed`, `merge_queue_stuck`; new
  `_evaluate_pr_timeline_alerts()` wired into `evaluate_all_alerts`

## Deviations from spec
- **`sync_repo` integration deferred** — standalone module; follow-up needed to call
  `fetch_pr_timeline_batch` after the PR upsert batch in `github_sync.sync_repo`
- **`codeowners_bypass` column not set during sync** — `check_bypass()` is ready but needs
  to be wired into the sync flow together with CODEOWNERS fetch
- **Notification toggle fields** use `getattr(config, ..., True)` default — no `NotificationConfig`
  migration needed yet; admin UI can add them later without a DB change

## Blocked By
- None

## Blocks
- 10-dora-v2-ai-cohort

## Soft dependency

Phase 07 (bottleneck intelligence) is softly dependent on this phase. 07 ships fine without 09
but gains sharper signals when 09 is live: cycle-time stage breakdown uses `ready_for_review_at`
instead of `first_review_at`, bounce detection gains `force_push_count_after_first_review` on
top of `review_round_count`, and merge-queue gate latency becomes measurable. Not a hard block —
07 is listed only in this note, not the Blocks list above, so work order is flexible.

## Parallelization note

This phase is independent of Linear sync work (Phase 01) and can run in parallel with it. Good
candidate for a second implementer while someone else takes 01.

## Description

Enrich GitHub PR ingestion with timeline events from GitHub's GraphQL `timelineItems` union. This
unlocks the strongest bounce signal (force pushes after first review), precise review-queue
latency (review_requested → reviewed), draft/ready transitions, merge queue gate latency, and
CODEOWNERS bypass detection. Without these, Phase 07's cycle-time-stage breakdown and Phase 10's
DORA v2 rework rate are impossible. Research shows a single GraphQL query can fetch 50 PRs worth
of timeline at a cost of ~8 points — very cheap.

## Deliverables

### backend/app/models/models.py

- **`PRTimelineEvent`** (table `pr_timeline_events`)
  - id (pk), pr_id FK→pull_requests (CASCADE), external_id (unique GitHub node_id),
    event_type (string — `review_requested`, `review_request_removed`, `review_dismissed`,
    `assigned`, `unassigned`, `labeled`, `unlabeled`, `head_ref_force_pushed`,
    `ready_for_review`, `converted_to_draft`, `renamed_title`, `cross_referenced`,
    `added_to_merge_queue`, `removed_from_merge_queue`, `auto_merge_enabled`,
    `auto_merge_disabled`, `marked_as_duplicate`), created_at,
    actor_developer_id FK→developers (SET NULL, nullable), actor_github_username,
    subject_developer_id FK→developers (SET NULL, nullable — e.g. review_requested target),
    subject_github_username (nullable),
    before_sha (varchar(40), nullable — for force_push), after_sha (varchar(40), nullable),
    data (JSONB — raw event data: label names, rename from/to, cross-ref target, dismissal
    message, queue position)
  - Indexes: `(pr_id, event_type, created_at)`, `(event_type, created_at)`,
    `(actor_developer_id, created_at)`
  - UniqueConstraint(external_id)

- **Extend `pull_requests`** with computed columns:
  - `force_push_count_after_first_review` (int, default 0) — derived count of
    `head_ref_force_pushed` events after `first_review_at`
  - `review_requested_count` (int, default 0) — distinct reviewer requests
  - `ready_for_review_at` (datetime, nullable) — true start of review cycle (replaces the
    draft-era `created_at` for queue-time calculations)
  - `draft_flip_count` (int, default 0) — `ready_for_review` + `converted_to_draft` transitions
  - `renamed_title_count` (int, default 0) — scope-thrash signal
  - `dismissed_review_count` (int, default 0) — reviews dismissed after being submitted
  - `merge_queue_waited_s` (int, nullable) — merge queue gate latency
  - `auto_merge_waited_s` (int, nullable) — auto-merge gate latency
  - `codeowners_bypass` (bool, default false) — set when merged with `reviewDecision != APPROVED`

### backend/app/services/github_sync.py

- New module `backend/app/services/github_timeline.py`:
  - `fetch_pr_timeline_batch(client, repo_owner, repo_name, pr_numbers: list[int])` —
    GraphQL query batching up to 50 PRs per request; returns timeline items per PR
  - `persist_timeline_events(db, pr, timeline_nodes)` — upsert events, resolve actor via
    existing `resolve_author` pattern
  - `derive_pr_aggregates(db, pr)` — computes the extension columns on `pull_requests` from
    the newly stored timeline events; called after timeline persist

- Integration into `sync_repo` (github_sync.py):
  - Add a post-PR-upsert step: collect PR numbers touched this sync batch, call
    `fetch_pr_timeline_batch` in 50-sized chunks
  - Respect existing `BATCH_SIZE = 50` PR commit boundary
  - Smart-skip: if a PR's `updated_at` hasn't changed, skip timeline fetch
  - Rate-limit awareness: read `rateLimit { cost remaining resetAt }` in every GraphQL
    response, back off at <10% remaining

- Integration into `SyncContext`:
  - Extend to carry `graphql_client` alongside existing REST `client`
  - Track `timeline_events_synced` in `sync_event.log_summary`

### backend/app/api/webhooks.py

Extend existing GitHub webhook handler to listen for timeline-relevant events:
- `pull_request.synchronize` already triggers re-sync — no change
- `pull_request_review.submitted` / `dismissed`
- `pull_request.ready_for_review` / `converted_to_draft`
- `pull_request_review_thread.resolved` / `unresolved` — requires new listener

### backend/app/services/pr_cycle_stages.py (new)

Decompose PR cycle time into stages:
- `open_to_ready_s` — `ready_for_review_at - created_at` (draft duration)
- `ready_to_first_review_s` — `first_review_at - ready_for_review_at`
- `first_review_to_approval_s` — `approved_at - first_review_at`
- `approval_to_merge_s` — `merged_at - approved_at`
- `merge_to_deploy_s` — needs deploy workflow mapping (Phase 10)

Function `get_pr_cycle_stage_distribution(db, since, until, group_by='repo|team|all')` returns
p50/p75/p90 per stage. Used by Phase 07 bottleneck summary.

### backend/app/services/notifications.py

New alert types following existing dedup convention:
- `pr_review_ping_pong` — PR with `review_round_count > 3` still open
  Dedup key: `pr_review_ping_pong:pr:<pr_id>`
- `pr_force_push_after_review` — `force_push_count_after_first_review >= 2` on open PR
  Dedup key: `pr_force_push_after_review:pr:<pr_id>`
- `codeowners_bypassed` — merged PR with `codeowners_bypass = true`
  Dedup key: `codeowners_bypassed:pr:<pr_id>`
- `merge_queue_stuck` — PR sitting in merge queue > 30 min
  Dedup key: `merge_queue_stuck:pr:<pr_id>`

### CODEOWNERS detection

- New `backend/app/services/codeowners.py`:
  - `fetch_codeowners(client, owner, repo)` — hits `/repos/{owner}/{repo}/contents/.github/CODEOWNERS`
    with path fallbacks (`/CODEOWNERS`, `/docs/CODEOWNERS`)
  - `parse_codeowners(text)` → list of (pattern, owners)
  - `check_bypass(pr, codeowners, reviews)` — was a matching owner among the approvers? If not and
    PR merged with `reviewDecision != APPROVED`, set `codeowners_bypass = true`
  - Run after timeline persist

### backend/tests/

- `tests/services/test_github_timeline_sync.py`: mock GraphQL response, verify event upsert,
  force-push count derivation, rename count, draft flip count
- `tests/services/test_pr_cycle_stages.py`: stage breakdown math, null-handling for PRs that
  never left draft, PRs merged without approval
- `tests/services/test_codeowners.py`: pattern parsing, bypass detection
- Integration test: full sync of a repo with seeded timeline events, then query stage
  distribution and verify per-stage counts

### frontend

No new page — data surfaces via existing pages:
- Phase 07 Bottlenecks page consumes `get_pr_cycle_stage_distribution`
- Phase 07 summary card lists new alert types alongside existing ones
- Existing PR detail view (if any) gains a "Timeline" section — optional, stretch goal

### docs/architecture/DATA-MODEL.md

- Document `pr_timeline_events` + extended `pull_requests` columns
- Note: GitHub's `/actions/runs/{id}/timing` endpoint is being deprecated — implementer should
  verify current state at build time and plan fallback via `/actions/runs/{id}/jobs`

## Sync cost audit

Record in PR description:
- GraphQL points consumed per full repo timeline fetch
- Wall-clock time vs pre-phase sync
- Row count in `pr_timeline_events` after first full sync

## Acceptance criteria

- [ ] Full sync populates `pr_timeline_events` for open and recently-closed PRs (deferred —
      needs `sync_repo` integration)
- [ ] Incremental sync uses smart-skip on PR `updated_at` (deferred)
- [x] `force_push_count_after_first_review` correctly identifies bounces (seeded test)
- [x] `ready_for_review_at` set correctly on PRs that were created as drafts
- [x] Merge queue + auto-merge gate latencies computed correctly
- [x] CODEOWNERS parse handles wildcards, team owners, and @user owners; bypass detection
      works on a seeded repo
- [x] Four new alert types wired into `evaluate_all_alerts`
- [x] Cycle-stage distribution endpoint returns correct p50/p75/p90 per stage for a seeded
      dataset
- [ ] GraphQL rate-limit budget consumption documented in PR (deferred — needs live sync run)
