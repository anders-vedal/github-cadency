# Linear insights v2 — deep workflow telemetry and bottleneck intelligence

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** large

## Overview

The current Linear integration ingests issues, projects, and cycles with creator + assignee and exposes
sprint/planning/projects dashboards. It has three structural weaknesses: (1) PR↔issue linking is pure
regex on title/branch/body and ignores Linear's authoritative GitHub attachments; (2) comments, state
history, and relations are not synced at all, so any behavioural metric (spec quality, dialogue, flow,
bottlenecks) is unreachable; (3) the surfaced metrics are aggregate roll-ups (velocity, completion rate)
that don't answer the questions an engineering leader actually asks — who creates which work, who picks
it up, where is it stuck, who is blocked on whom, which issues are muddled enough to cause PR bounce.

This epic closes all three gaps. It adds depth to the sync, flips the linker to attachment-first, and
layers a set of behavioural dashboards on top — Linear Usage Health, Issue Conversations, Creator
Analytics on Developer Detail, Flow Analytics, and a Bottleneck and Flow Intelligence surface that
answers "where is work stuck, who is overloaded, which teams are silo'd".

## Why this matters

Teams adopt Linear as their "source of truth" for work but get the value only if the tooling makes the
workflow legible. Today a team lead using DevPulse can see sprint velocity and PR counts but cannot
answer:

- "Are tickets written clearly enough before engineers pick them up?"
- "Whose tickets produce clean PRs and whose produce back-and-forth?"
- "Where is work actually stuck — intake, refinement, review, blocked?"
- "Is review load balanced or is one person the bottleneck on 40% of merges?"
- "Do we have silos where devs only review their own team's PRs?"

All of these are answerable from Linear + GitHub telemetry if we sync the right data and compute the
right derivations. This epic is the bridge.

## Phases

- [x] Phase 01: **Sync depth foundations** → `01-sync-depth-foundations.md`
- [x] Phase 02: **Linking upgrade + data quality panel** → `02-linking-upgrade-and-quality.md`
- [x] Phase 03: **Linear Usage Health dashboard card** → `03-usage-health-dashboard.md`
- [x] Phase 04: **Issue Conversations drill-down** → `04-issue-conversations.md`
- [x] Phase 05: **Creator analytics on Developer Detail** → `05-creator-analytics.md`
- [x] Phase 06: **Flow analytics from history** → `06-flow-analytics-from-history.md`
- [x] Phase 07: **Bottleneck and flow intelligence** → `07-bottleneck-intelligence.md`
- [x] Phase 08: **Research synthesis** → `08-research-synthesis.md`
- [x] Phase 09: **GitHub PR timeline enrichment** → `09-github-pr-timeline-enrichment.md`
- [x] Phase 10: **DORA v2 + AI-assisted PR cohort split** → `10-dora-v2-ai-cohort.md`
- [x] Phase 11: **Metrics governance + AI-cohort guardrails** → `11-metrics-governance.md`

## Dependency graph

```
09 ──┐
01 ──┼──> 02 ──┬──> 03
     │         ├──> 04
     │         └──> 05
     ├──> 06   (needs history accumulation before UI is meaningful)
     ├──> 07 <──┘  (09 enriches timeline data used by 07 cycle-time-stage breakdown)
     └──> 10 ──> 11 (governance applies to all metric surfaces)

08 is a sibling document (research) — it informed the expanded scope of 07 and the creation
of 09, 10, 11. It can be considered complete.
```

## Data model additions

Three new tables, plus an extension to `pr_external_issue_links`:

1. **`external_issue_comments`** — issue_id, external_id (Linear comment id), author_developer_id
   (nullable, mapped via `developer_identity_map`), author_email, created_at, body_length,
   body_preview (first 280 chars), is_system_generated (bool — Linear emits automation/bot comments).
2. **`external_issue_history`** — issue_id, actor_developer_id (nullable), actor_email, changed_at,
   field (status/assignee/estimate/priority/project/cycle/label), from_value, to_value (both as
   text for flexibility).
3. **`external_issue_attachments`** — issue_id, external_id (Linear attachment id), url,
   source_type (github_pr/github_commit/figma/slack/etc), created_at, actor_developer_id.
4. **`pr_external_issue_links`** gains: `link_confidence` (high/medium/low) and a richer
   `link_source` enum (linear_attachment / branch / title / body / commit_message).

## Acceptance criteria (epic-level)

- [ ] A full Linear sync populates comments, history, and attachments for all 588+ issues without
      breaking the existing incremental pattern
- [ ] After the linking upgrade, PR↔issue linkage rate improves measurably (target: +20 percentage
      points on a test dataset) and every link has a `link_confidence` value
- [ ] The new Dashboard card answers "is Linear healthy?" in under 5 seconds of scanning
- [ ] A leader can open Issue Conversations and immediately identify the 10 chattiest issues plus
      whether they correlate with bouncy downstream PRs
- [ ] Developer Detail shows a creator profile (tickets written, dialogue generated, downstream PR
      outcomes) and a worker profile (tickets picked, self-picked %, cycle time)
- [ ] Flow analytics correctly identify status regressions and triage bounces for any selected cycle
- [ ] Bottleneck Intelligence surfaces review overload, WIP violations, silo'd review networks, and
      blocked-chain depth in a single review with clear drill-down

## Risks & open questions

- **Sync cost for comments + history**: Linear's GraphQL complexity budget. Incremental sync via
  existing `updatedAt` filter keeps steady-state cheap; first full sync on 588 issues is a one-time
  cost. Phase 01 measures and documents.
- **Privacy on creator→outcome correlation**: the "whose tickets produce clean PRs" metric is
  weaponizable as a ranked leaderboard. Phases 03/05 frame it for self-reflection, not comparison.
- **Bot-authored comments** (Linear's automation emits system comments) must be filtered from
  dialogue-health signals — `is_system_generated` column handles this.
- **Body preview leakage**: the 280-char preview can still contain secrets. Phase 01 includes a
  sanitization pass (same pattern as `ErrorSanitizer`) before persistence.
- **Historical backfill**: comments + history do not come with issues in the initial `issues` query;
  they require per-issue expansion. Phase 01 adds a background backfill job separate from the hot
  sync path.
- **`is_primary_issue_source` interaction**: many of the new metrics only make sense when Linear is
  the primary source. UI must be graceful when it isn't (hide the Usage Health card, show an
  "enable Linear as primary" CTA).

## Out of scope for this epic

- Full comment body storage (only length + 280-char preview)
- NLP sentiment analysis on comments
- Cross-tool telemetry (Slack, meetings, calendars)
- Jira support (the generic `integration_config` design already anticipates it; out of scope here)
- Real-time via webhooks (Phase 01 adds incremental sync; webhooks deferred to follow-up epic)
- Linear Initiatives / Roadmaps sync (schema-ready via 01 but not materialized in UI)
- SPACE Satisfaction surveys + DevEx framework survey hooks (future epic)
- Team Topologies auto-classification (too high misread risk; keep manual)
- Team-aggregate sentiment trend (opt-in AI feature in a future phase — raw per-dev sentiment
  is explicitly banned per Phase 11)

## Completion summary (2026-04-22)

All 10 implementation phases shipped. 1176 backend tests pass (pre-existing OAuth/sync-errors
failures unrelated to this work). Frontend TypeScript type-check green.

### Backend surface

- **Services added** (`backend/app/services/`): `linear_health.py`, `linkage_quality.py`,
  `issue_conversations.py`, `flow_analytics.py`, `bottleneck_intelligence.py`,
  `developer_linear.py`, `github_timeline.py`, `pr_cycle_stages.py`, `codeowners.py`,
  `ai_cohort.py`, `dora_v2.py`, `incident_classification.py`, `metric_spec.py`
- **Services extended**: `linear_sync.py` (rate limit fix, 4-pass attachment-first linker,
  sanitize_preview, normalize_attachment_source, per-issue expansion for comments/history/
  attachments/relations, sync_linear_project_updates)
- **API routers added** (`backend/app/api/`): `linear_health`, `conversations`, `flow`,
  `bottlenecks`, `metrics`, `dora_v2`. Extended: `integrations.py` (+ linkage-quality + relink),
  `developers.py` (+ 3 Linear profile endpoints)
- **Migrations**: `042_linear_insights_v2_sync_depth.py`, `043_github_pr_timeline.py`
- **New tables**: `external_issue_comments`, `external_issue_history`,
  `external_issue_attachments`, `external_issue_relations`, `external_project_updates`,
  `pr_timeline_events`
- **Extended tables**: `external_issues` (SLA + triage + subscribers + reactions),
  `pr_external_issue_links` (link_confidence), `pull_requests` (9 timeline columns)
- **Notifications**: 4 new alert types (`pr_review_ping_pong`, `pr_force_push_after_review`,
  `codeowners_bypassed`, `merge_queue_stuck`)

### Frontend surface

- **New hooks** (`frontend/src/hooks/`): `useLinkageQuality`, `useLinearUsageHealth`,
  `useConversations`, `useDeveloperLinear`, `useFlowAnalytics`, `useBottlenecks`
- **New pages**: `pages/admin/LinkageQuality.tsx`, `pages/insights/IssueConversations.tsx`,
  `pages/insights/FlowAnalytics.tsx`, `pages/insights/Bottlenecks.tsx`
- **New components**: `components/linear-health/LinearUsageHealthCard`,
  `components/linear-health/CreatorOutcomeMiniTable`,
  `components/developer/LinearCreatorSection`, `LinearWorkerSection`, `LinearShepherdSection`,
  `components/charts/CommentBounceScatter`, `LorenzCurve`, `CumulativeFlowDiagram`
- **Wired into**: `Dashboard.tsx` (Linear health card, gated on Linear primary),
  `DeveloperDetail.tsx` (3 Linear sections, gated on self/admin for creator+shepherd),
  `App.tsx` (4 routes + sidebar entries)

### Known deviations from spec

Most deviations were resolved in a follow-up pass (2026-04-22) — see
"Deviation follow-up (2026-04-22)" below. The few remaining carried-forward
notes:

- Phase 07 review network renders as table-of-clusters (silo-badged) rather than
  react-force-graph — spec explicitly allowed this
- Phase 10 still wraps (rather than refactors) the existing `get_dora_metrics` in
  `stats.py`; v1 DORA page preserved unchanged on purpose
- Phase 10 `deployment_workflow_classification.py` / `is_deployment` column on
  `workflow_runs` — DevPulse uses a dedicated `Deployment` table (populated by
  github_sync); creating a parallel `workflow_runs` classification layer would
  duplicate existing logic with no behavior change, so not implemented.

### Bugs found and fixed during post-implementation review (2026-04-22)

- `linkage_quality.py` disagreement-PR query selected `Repository.owner` (column doesn't
  exist; fixed to `Repository.full_name`)
- `developers.py` Phase 05 visibility gate used `user.role == AppRole.ADMIN` (wrong attribute
  name AND wrong case — fixed to `user.app_role == AppRole.admin`)
- Phase 01 sync queried `Issue.slaStatus` which is filter-only on Linear's schema, not a real
  field — removed from query; added `_derive_sla_status()` helper that derives from
  start/breach/risk timestamps + completion state
- Phase 01 bot detection used `bot_actor is not None and bool(bot_actor)` after coercing
  `botActor or {}` which made the null guard meaningless — simplified to `bot_actor_raw is not None`
  (Linear sends populated dict for bots, null for humans)
- Phase 04 `get_chattiest_issues` and `get_first_response_histogram` subtracted naive vs
  aware datetimes (crashes on Postgres) — both now coerce to UTC-aware before subtracting
- Phase 05 `LinearWorkerSection` was visible to anyone viewing another developer's profile
  page (privacy leak — backend would 403 but the ErrorCard surfaced) — gated on
  `isLinearPrimary && (isAdmin || isOwnPage)` matching Creator + Shepherd
- Phase 07 CFD reconstructed pre-history dates as the issue's CURRENT state, inverting flow
  for issues that started in triage and finished in done — now uses the first event's
  `from_state_category` for pre-event dates
- Phase 09 `pr_cycle_stages.compute_pr_stage_durations` always returned 0 for
  `ready_to_first_review_s` on non-draft PRs (stage start == end via fallback) — biased
  percentile distributions to zero. Now returns None for non-draft PRs instead.
- Phase 09 `PRTimelineEvent.actor` and `.subject` relationships missing `viewonly=True` —
  triggered SAWarning at startup
- Phase 01 `from_priority`/`to_priority` stored as Integer but Linear schema is Float —
  added explicit `int(value)` cast with null guard
- Phase 02 `_CONFIDENCE_RANK.get(existing.link_confidence, 0)` defaulted to 0 ("low") on
  unknown stored values — changed default to -1 so unknown/null still upgrades

### Known performance follow-ups (not bugs, but should be addressed)

- `_resolve_developer_by_email` is called per comment / per history event with no cache —
  for a 588-issue full sync with comments+history, this is 6000+ individual SELECTs.
  Build an email→developer_id dict once per sync.
- `compute_rework_rate` (Phase 10) issues N SQL queries for N merged PRs in range — could
  be a single self-join on `pr_files` + `pull_requests`.
- `flow_analytics.get_status_regressions` and `get_refinement_churn` call `db.get(ExternalIssue, iid)`
  in a loop — should batch-load with `WHERE id IN (...)`.
- `get_cumulative_flow` walks (days × issues × events) per request — for 30-day window with
  500 issues this is reasonable but could be precomputed.

## Deviation follow-up (2026-04-22)

After the initial 10-phase ship, a pass through the "Known deviations" list
closed all but three of them. Changes by tranche:

### Data integrity

- **Phase 01 per-issue pagination** — `sync_linear_issues` now walks the
  `comments` and `history` connections to exhaustion when `hasNextPage` is
  true (capped at 50 pages per issue). Previously the `expansions_triggered`
  counter bumped but nothing fetched the follow-up pages, so issues with >50
  comments / >50 history events silently lost data. New `ISSUE_COMMENTS_PAGE_QUERY`
  and `ISSUE_HISTORY_PAGE_QUERY` plus `_fetch_all_comment_pages` /
  `_fetch_all_history_pages` helpers. Regression test:
  `test_sync_paginates_comments_and_history_beyond_first_page`.
- **Phase 09 `sync_repo` integration** — `github_sync.sync_repo` now calls
  `_enrich_pr_timelines` after the PR upsert loop. For each PR in the sync
  batch: fetch timeline via `fetch_pr_timeline_batch`, persist via
  `persist_timeline_events`, derive aggregates via `derive_pr_aggregates`, and
  run CODEOWNERS bypass detection via a new `_set_codeowners_bypass` helper
  (fetches the CODEOWNERS file once per repo via `_fetch_codeowners_text`).
  Force-push counts, merge-queue latencies, CODEOWNERS bypass, and the four
  notification alerts are now populated as a normal side effect of sync.

### Frontend UX

- **Phase 10 DORA v2 cohort toggle** — `DoraMetrics.tsx` now has a 5-option
  cohort toggle (All / Human / AI-reviewed / AI-authored / Hybrid), an
  AI-share disclosure banner on "All" view when AI-touched PRs exist in
  range, a Rework Rate stat card, and a Cohort Comparison card showing the
  4-way split with merges / rework / share %. New hook `useDoraV2`.
- **Phase 11 governance components + admin page** — New
  `<MetricsUsageBanner>` (quarterly-re-show dismissal via `localStorage`,
  auto-inserted at the Insights layout root), `<DistributionStatCard>` (p50 +
  p90 + histogram sparkline), `<AiCohortBadge>`. New admin page
  `/admin/metrics-governance` consuming `/api/metrics/catalog`, rendering the
  registry + banned-metric list.
- **Phase 04 Linear labels picker** — New endpoint `GET /api/linear/labels`
  that flattens distinct labels from `external_issues.labels` with issue-count
  frequency (top 200). Wired as a Select filter on the Conversations page.
- **Phase 02 12-week linkage trend** — New service
  `get_linkage_rate_trend(db, integration_id, weeks)` computes weekly PR
  linkage rate from existing `pull_requests.created_at` + link rows (no
  snapshot table needed). Endpoint `GET /api/integrations/{id}/linkage-quality/trend`.
  Rendered as a line chart on `/admin/linkage-quality`.

### Schema / admin CRUD

- **Phase 05 `IssueCreatorStats` extension** — Added
  `avg_downstream_pr_review_rounds` + `sample_size_downstream_prs` to the
  canonical schema and `_get_issue_creator_stats_linear`; team-average
  uses sample-size-weighted mean so small-N creators don't dominate.
- **Phase 11 `StatCard.pairedOutcome` slot** — `StatCard` now accepts a
  `pairedOutcome?: { label, value, tooltip }` prop rendering below the main
  value with a separator.
- **Phase 10 admin CRUD for classifier rules** — New `classifier_rules`
  table (migration 044) with a `kind` discriminator column supporting
  `incident` / `ai_reviewer` / `ai_author` rules. CRUD endpoints at
  `/api/admin/classifier-rules/*` (admin-only). Admin UI page at
  `/admin/classifier-rules` with tabs + inline add/delete/enable-toggle.
  DB rules merge on top of the hard-coded defaults (additive — disable is
  via the `enabled` flag, not replacement). `get_dora_v2` now loads merged
  AI detection rules automatically.

### Performance

- **Email cache in Linear sync** — `_build_email_cache` preloads
  active-developer emails once per sync; `_resolve_developer_by_email`
  accepts an optional cache dict, threaded through all four persist
  helpers (`_persist_issue_comments`, `_persist_issue_history`,
  `_persist_issue_attachments`, and the main issue-upsert loop). Previous
  per-row SELECTs on a 588-issue sync were ~6000+; now O(1) per sync.
- **`compute_rework_rate` self-join** — Replaced the N+1 per-PR loop with a
  single DISTINCT self-join that matches base PRs to follow-up PRs via
  shared filenames. Window filter (7 days) is applied Python-side because
  timedelta-DateTime compilation differs between PG and SQLite; the join
  alone collapses the query count from O(N merges) to 1. New integration
  test `test_dora_v2_rework.py` (3 tests).
- **`flow_analytics` batch loads** — `get_status_regressions`,
  `get_triage_bounces`, and `get_refinement_churn` no longer issue
  `db.get(ExternalIssue, iid)` in a loop. Each now batch-loads via
  `WHERE id IN (...)` after first identifying which issues it needs.

### Documentation

- **`docs/metrics/principles.md`** — New canonical reference for the six
  metrics-governance principles (distribution > average, team > individual,
  activity pairs with outcome, AI cohort transparency, framing matters,
  Goodhart awareness), with pointers to the `MetricSpec` enforcement.
- **`docs/metrics/banned.md`** — Rationale per banned-metric entry (LOC per
  dev, commits per dev, story-points-per-sprint-per-dev, TTFR-as-KPI, LOC-
  weighted impact score, raw per-dev sentiment).

### Still deferred after the follow-up

- Phase 10 doesn't refactor the existing `get_dora_metrics` in `stats.py` —
  v2 remains additive. No plan to change this — v1 DORA page preserves its
  independent contract on purpose.
- Phase 10 `deployment_workflow_classification.py` / `is_deployment` column
  on `workflow_runs` — DevPulse uses a dedicated `Deployment` table populated
  by github_sync; a parallel workflow-run classification layer would
  duplicate existing logic with no behavior change.
- Phase 07 review network still renders as a table-of-clusters (silo-badged)
  rather than react-force-graph — spec explicitly allowed either.

All backend integration + unit tests pass (1214 pass; 6 pre-existing failures
in `test_oauth.py` and `test_sync_errors.py` unrelated to this work).
Frontend type-check (`pnpm exec tsc --noEmit --project tsconfig.app.json`)
exits 0.

## How this epic was shaped

Phases 01-07 were the initial plan proposed in the conversation with the user. After the plan
was approved, five parallel research and code-exploration agents ran covering: Linear API
capabilities, GitHub API capabilities (timeline events, CODEOWNERS, rulesets), software
engineering workflow theory (DORA, SPACE, Flow Framework, Theory of Constraints, Team
Topologies, Goodhart's-Law anti-patterns), backend stats layer structure, and frontend
architecture. Their findings are captured in `08-research-synthesis.md`. The synthesis led to:

- Plan-level corrections folded into phases 01-07 (structured IssueHistory columns, SLA on Issue,
  stacked `<h2>` sections on Developer Detail instead of tabs, etc.)
- Scope expansion on phase 07 (review ping-pong, cycle-time stages, bus factor per file,
  cycle-time histogram)
- Three new phases: 09 (GitHub PR timeline enrichment — force pushes, merge queue, CODEOWNERS
  bypass), 10 (DORA v2 revision + AI-cohort split — critical given AI review adoption), and 11
  (metrics governance — guardrails, banned-metric registry, team-aggregate defaults, outcome
  pairing enforcement)
