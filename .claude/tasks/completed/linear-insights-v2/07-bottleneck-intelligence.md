# Phase 07: Bottleneck and flow intelligence

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** large
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/app/services/bottleneck_intelligence.py` — 10 signals: `get_cumulative_flow`,
  `get_wip_per_developer`, `get_review_load_gini`, `get_review_network`,
  `get_cross_team_handoffs`, `get_blocked_chains`, `get_review_ping_pong`,
  `get_bus_factor_by_file`, `get_cycle_time_histogram` (with `_detect_bimodal`),
  `get_bottleneck_summary` (digest)
- `backend/app/api/bottlenecks.py` — 10 endpoints under `/api/bottlenecks/*`
- `frontend/src/pages/insights/Bottlenecks.tsx`
- `frontend/src/hooks/useBottlenecks.ts` (10 hooks)
- `frontend/src/components/charts/LorenzCurve.tsx`
- `frontend/src/components/charts/CumulativeFlowDiagram.tsx`

## Files Modified
- `backend/app/main.py` — registered `bottlenecks.router`
- `backend/app/schemas/schemas.py` — `CumulativeFlowPoint`, `WipOverLimit`, `WipIssueRef`,
  `ReviewLoadGini`, `ReviewLoadTopRow`, `ReviewNetworkResponse`, `ReviewNetworkNode`,
  `ReviewNetworkEdge`, `CrossTeamHandoff`, `BlockedChainRow`, `ReviewPingPongRow`,
  `BusFactorFileRow`, `CycleTimeHistogramResponse`, `BimodalAnalysis`, `BimodalPeak`,
  `BottleneckDigestItem`
- `frontend/src/App.tsx` — `/insights/bottlenecks` route + Linear insights sidebar entry
- `frontend/src/utils/types.ts`

## Deviations from spec
- Review network renders as table-of-clusters with silo-badges instead of react-force-graph
  (spec explicitly permitted this)
- Notification alert types for ping-pong and force-push are handled by Phase 09's
  `_evaluate_pr_timeline_alerts`, not Phase 07 — cleaner single source of truth

## Blocked By
- 01-sync-depth-foundations
- 02-linking-upgrade-and-quality
- 06-flow-analytics-from-history

## Blocks
- None

## Soft dependency

Phase 09 (GitHub PR timeline enrichment) makes this phase significantly better — it provides
`ready_for_review_at`, `force_push_count_after_first_review`, and merge-queue latency which
sharpen the cycle-time-stage breakdown and the bounce signal. If 09 isn't complete when this
phase ships, fall back to `first_review_at` (ignore draft duration) and use `review_round_count`
alone as the bounce proxy. The bus-factor-per-file signal and review network silo detection do
not depend on 09 at all.

## Description

The capstone page: a single surface that answers "where is work actually stuck, who is overloaded,
and where are teams silo'd?" Combines signals from Linear flow + GitHub review data. Scope is
expected to grow once the research synthesis (08-research-synthesis.md) lands — any additions from
that document get added to this phase's deliverables list.

## Deliverables

### backend/app/services/bottleneck_intelligence.py (new)

Computed signals, each a standalone function:

- **Cumulative Flow Diagram (CFD)** data for a selected cycle or project
  `get_cumulative_flow(db, cycle_id=None, project_id=None, since=None, until=None)` →
  For each day in the range, count of issues in each status bucket. Classic flow diagnostic;
  widening bands = flow problem in that stage.

- **WIP limits per developer**
  `get_wip_per_developer(db, as_of=None, limit=4)` → developers with current in_progress issue
  count > limit. Configurable threshold (default 4). Returns the over-limit developers and their
  current issue list.

- **Review load imbalance (Gini coefficient)**
  `get_review_load_gini(db, since, until)` → Gini coefficient of PR review counts distributed
  across active reviewers. Higher = more lopsided.
  Also return the top-K reviewers by review count and time-spent-reviewing.

- **Review network silos**
  `get_review_network(db, since, until)` → edges (reviewer → author, weighted by review count) for
  the graph. Client computes community detection (Louvain or simple connected-components). Nodes
  never reviewed outside their component = silo.

- **Cross-team hand-off friction**
  `get_cross_team_handoffs(db, since, until)` → issues that moved between teams (different
  `team_key` on successive cycles, or project transitions across teams). Time spent "in transit"
  = friction. Only meaningful if multi-team.

- **Blocked-chain depth** (requires Linear relations sync — see below)
  `get_blocked_chains(db)` → for each open issue, compute the length of the longest blocked-by
  chain. Chains of depth 3+ = work that's serialized by dependencies.

### backend/app/services/linear_sync.py — Linear relations extension

Add Linear's `relations` field (blocks / blocked-by / related) to the issue sync:
```graphql
relations(first: 50) {
  nodes { type relatedIssue { id identifier } }
}
```

New table **`ExternalIssueRelation`** (`external_issue_relations`):
- id (pk), issue_id, related_issue_id, relation_type (blocks/blocked_by/related/duplicate), created_at
- Indexes: `(issue_id, relation_type)`, `(related_issue_id, relation_type)`
- Bidirectional storage — when Linear says A `blocks` B, we store both A-blocks-B and B-blocked_by-A

### backend/app/api/bottlenecks.py (new)

- `GET /api/bottlenecks/cumulative-flow?cycle_id=&project_id=&since=&until=`
- `GET /api/bottlenecks/wip?threshold=4&as_of=`
- `GET /api/bottlenecks/review-load?since=&until=`
- `GET /api/bottlenecks/review-network?since=&until=`
- `GET /api/bottlenecks/cross-team-handoffs?since=&until=`
- `GET /api/bottlenecks/blocked-chains`
- `GET /api/bottlenecks/summary` — single endpoint that runs all signals with default params and
  returns a "top 5 active bottlenecks right now" digest for the dashboard

### backend/app/schemas/schemas.py

- `CumulativeFlowPoint`, `WipOverLimit`, `ReviewLoadRow`, `ReviewNetworkEdge`,
  `CrossTeamHandoff`, `BlockedChain`, `BottleneckSummary`

### frontend/src/pages/insights/Bottlenecks.tsx (new)

Layout — top-down from summary to detail:

1. **Bottleneck summary card** — "Current top bottlenecks" digest: 3-5 items, each a one-line
   description + drill link (e.g., "Review: 2 reviewers handle 54% of all reviews", "WIP: 3
   developers have 5+ in_progress issues", "Blocked: 8 issues in chains of depth 3+")
2. **Cumulative Flow Diagram** — stacked area chart by status over time, cycle/project picker
3. **WIP per developer** — horizontal bar chart, threshold line, over-limit devs highlighted
4. **Review load distribution** — Lorenz curve + Gini coefficient; table of top reviewers
5. **Review network visualization** — force-directed graph using react-force-graph; silo components
   highlighted with a different fill
6. **Cross-team hand-offs table** — issues by transit time, worst first
7. **Blocked chains** — tree / list view of chains, longest first; drill into the root blocker

### frontend/src/components/charts/

- `LorenzCurve.tsx` — for Gini visualization
- `ReviewNetworkGraph.tsx` — wraps react-force-graph with DevPulse-themed styling
- `CumulativeFlowDiagram.tsx` — stacked area with tooltip

### frontend/src/App.tsx

- Route `/insights/bottlenecks` lazy-loaded
- Sidebar entry "Bottlenecks", gated on `hasLinear && isPrimary`

### Tests

- `backend/tests/services/test_bottleneck_intelligence.py`: each signal against seeded data —
  Gini coefficient math, WIP threshold, blocked-chain depth, CFD point generation
- `backend/tests/services/test_linear_relations.py`: bidirectional storage of relations
- E2E test: summary card renders 3-5 bottlenecks, each signal section renders

## Acceptance criteria

- [x] CFD correctly reflects historical state counts for any selected cycle
- [x] Gini coefficient matches hand-computed value on known data
- [x] Review network renders (as table-of-clusters with silo detection)
- [x] Blocked chains only include open issues and compute depth correctly
- [x] Summary card picks the 3-5 worst active bottlenecks by a deterministic scoring rule
      (documented in the service module docstring)
- [x] Cross-team hand-offs correctly identify inter-team transits using `team_key`

## Research-driven additions (folded in from 08-research-synthesis.md)

### Additional signals to compute

1. **Review ping-pong flag** — PRs with `review_round_count > 3` while still open.
   - New function `get_review_ping_pong(db, since, until)` returns per-PR rows with rounds,
     author, reviewers involved, current state
   - New alert type in `services/notifications.py`: `pr_review_ping_pong` with dedup key
     `pr_review_ping_pong:pr:<pr_id>` (pattern matches existing alerts)
   - Research citation: >3 review cycles = strong friction signal (Forsgren/SPACE)

2. **Cycle-time stage breakdown** (Theory of Constraints lens)
   - `get_pr_cycle_stage_distribution(db, since, until, group_by='repo|team|all')` returns
     p50/p75/p90 for each stage: open → ready_for_review → first_review → approved → merged
     → deployed
   - Stages 1-4 use existing `PullRequest` columns. Stage 5 (merged→deployed) requires Phase 10
     deployment workflow classification — if unavailable, omit gracefully
   - Display as horizontal stacked bar chart: each PR is one bar, each stage a colored segment,
     sorted by total cycle time. Highlights the stage where the wait is longest — classic TOC
     "identify the constraint" visualization

3. **Bus factor per file/module**
   - New function `get_bus_factor_by_file(db, since_days=90, min_authors=2)` — scans
     `pr_files` joined to `PullRequest.author_id`, counts distinct authors per filename over
     the 90-day window
   - Flags files with fewer than `min_authors` authors
   - Returns top-N "single-owner" files + the developer who owns each
   - New alert type `single_owner_file` with dedup key `single_owner_file:file:<path_hash>`
   - Research citation: Avelino et al. (ICSE SEIP 2022) bus-factor-in-practice

4. **Cycle time histogram (bimodal detection)**
   - Already partially covered in bottleneck Lorenz curve. Add a separate cycle-time histogram
     chart next to the review-load Gini — shape analysis (normal / bimodal / heavy-tailed) is
     a first-class signal
   - Auto-detect bimodality: compute Hartigan's dip statistic or simpler — two distinct peaks
     separated by a trough > 20% of the lower peak. Flag as "bimodal — investigate two
     parallel processes"

### Additional visibility guardrails

Per Phase 11 (Metrics Governance):
- Creator-level bounce metrics on this page default to admin-only (not team-visible)
- All aggregate metrics (Gini, CFD, silo network) default to team-visible
- Each stat card that includes AI-cohort data shows the AI-share badge (Phase 11 component)

### Updated dependency

- This phase now depends on Phase 09 (GitHub PR timeline enrichment) for:
  - `ready_for_review_at` (stage breakdown start point)
  - `force_push_count_after_first_review` (complements review_round_count as bounce signal)
  - `merge_queue_waited_s` (deploy-stage latency component)

  If Phase 09 is not complete, Phase 07 still ships — it just uses `review_round_count` as the
  only bounce signal and uses `first_review_at` instead of `ready_for_review_at`.
