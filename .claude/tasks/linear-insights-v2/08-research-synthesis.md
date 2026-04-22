# Phase 08: Research synthesis

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** research
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2/00-overview.md

## Blocked By
- None

## Blocks
- None

## Note on sequencing

This file is a completed research artifact, not a work item. Its findings have already been
folded into Phase 01 (corrections) and Phases 07/09/10/11 (scope expansion / new phases). It
does not gate any other phase — keep it in the tree as documentation / rationale.

## Description

Synthesis of five parallel research + code-exploration efforts that ran while the initial v2 plan
was being scaffolded. Findings have been folded into earlier phase files where directly applicable;
this document captures the cross-cutting insights and the new phases (09-11) they generated.

## Research conducted

1. **Linear GraphQL API deep-dive** — schema, rate limits, webhooks, Insights gaps
2. **GitHub REST + GraphQL capabilities** — timeline events, CODEOWNERS, rulesets, merge queue,
   reactions, sub-issues
3. **Workflow theory** — DORA, SPACE, Flow Framework, Theory of Constraints, Team Topologies,
   spec-quality proxies, team-friction signals, Goodhart's-Law anti-patterns, 2024-2026 updates
   (AI code review cohort effects)
4. **DevPulse backend exploration** — stats.py function inventory, sync patterns, notification
   dedup convention, collaboration score pipeline, ORM FK/ondelete conventions
5. **DevPulse frontend exploration** — routing, SidebarLayout, insights-page template,
   Tab-component caveat, TanStack Query conventions, empty/error/loading patterns

## Key findings

### Plan-level corrections folded into existing phases

| # | Finding | Phase updated |
|---|---|---|
| 1 | `IssueHistory` has typed from/to columns — store structured, not generic from_value/to_value | 01 |
| 2 | SLA fields are on `Issue` directly — extend `external_issues`, no new table | 01 |
| 3 | Reactions via `reactionData` JSON — no Reactions table | 01 |
| 4 | `botActor` is the authoritative automation marker, not email patterns | 01 |
| 5 | Rate limit is HTTP 400 with `RATELIMITED` code, not HTTP 429 — likely latent bug in current code | 01 |
| 6 | `Attachment.sourceType == 'github'` with URL → `/pull/\d+` is the canonical PR-link signal | 01, 02 |
| 7 | `IssueRelation` (blocks/blocked-by/related/duplicate) — sync in Phase 01, use in Phase 07 | 01, 07 |
| 8 | `ProjectUpdate` is Linear's authoritative project-health narrative | 01 |
| 9 | DeveloperDetail page has NO tab system — use stacked `<h2>` sections, not a new tab | 05 |
| 10 | No `IntegrationsContext` — every page calls `useIntegrations()` directly | 03, 04, 05, 06, 07 |
| 11 | shadcn/ui primitives are base-ui (base-nova), Tabs use `data-active`, NOT Radix | 05 |
| 12 | `get_issue_creator_stats` already exists at stats.py:3025 with Linear branch — extend, don't duplicate | 05 |
| 13 | `_compute_per_developer_metrics` at stats.py:1051 is the batch benchmark engine — new creator metrics plug in here, not in a new service | 05 |
| 14 | `enhanced_collaboration.py` has a 5-signal pipeline (review, co-author, issue co-comments, mentions, co-assignment) — comment co-engagement on Linear issues should be an additive signal here, not a new table | (new Phase 11) |
| 15 | `_default_range` helper is in `services/utils.py`, imported as `default_range` — don't re-implement | all new services |
| 16 | Notification dedup key format is `{alert_type}:{entity_type}:{entity_id}` — new bottleneck alerts must follow | 07 |
| 17 | Default TanStack Query staleTime is 30s; include date params in query keys | all new hooks |

### Gaps that justify new phases

| Finding | Rationale | New phase |
|---|---|---|
| GitHub GraphQL `timelineItems` exposes `HeadRefForcePushedEvent`, `ReviewRequestedEvent`, `ReviewDismissedEvent`, `ReadyForReviewEvent`, merge-queue and auto-merge events — all of which are MUCH better signals than anything we compute from static PR fields | Force-push after first review is the strongest bounce signal; review-requested timing is better than "time to first review" for queue analysis; merge-queue gate latency is currently invisible. All derivable via a single GraphQL query per PR with cost ~8 points per 50 PRs. | **Phase 09: GitHub PR timeline enrichment** |
| DORA's 2024 revision moved MTTR into throughput, added rework rate, and AI adoption creates a bimodal cycle-time distribution that requires cohort splitting — existing DevPulse DORA metrics assume pre-AI signal shape | Without cohort split, AI-reviewed and AI-authored PRs blend with human ones, masking the actual process health. GitHub now ships a Copilot review metrics API; we should tag PRs and report cohorts separately. | **Phase 10: DORA v2 + AI-assisted PR cohort** |
| Every research source (DORA, SPACE, Team Topologies, Forsgren, Jellyfish, Haystack) emphasizes that engineering metrics are gamed when framed as individual performance and when activity-only metrics lack outcome pairing. The only safe product surface is team-aggregate + distribution-aware + paired | Without a guardrails layer, v2's creator-outcome and bottleneck metrics become weaponizable. Need a cross-cutting governance phase covering default permissions, banner copy, outcome-pairing enforcement in stats functions, and banned metrics. | **Phase 11: Metrics governance + AI-cohort guardrails** |
| Linear webhook events can drive near-real-time updates (Issue, Comment, Attachment, Project, ProjectUpdate, IssueSLA, etc.) with HMAC-SHA256 signatures — can drop sync latency from minutes to seconds | Polling is fine for bulk sync but webhooks unlock real-time dashboards and reduce complexity-budget pressure. Not blocking for v2 but worth planning. | **Deferred — post-epic follow-up** (not yet filed as a phase) |

### Workflow-theory-driven signals to add to Phase 07

Phase 07's original deliverables (CFD, WIP, Gini review load, review network silos, cross-team
hand-offs, blocked chains, summary digest) are strong. Research adds four signals worth including:

1. **Review ping-pong flag** — PRs with `review_round_count > 3`. We already store this column.
   Add as both a per-PR signal on the Bottlenecks page and a notification alert type.
2. **Cycle-time stage breakdown** — open → first_review → approved → merged → deployed.
   Theory of Constraints lens: show where the wait is longest, not just total cycle time.
   All fields already exist on `PullRequest`.
3. **Bus factor per file/module** — count distinct authors per file in 90-day window via
   `pr_files` + `commits`. Flag files with ≤1 author and on the critical path.
4. **Cycle time histogram (bimodal detection)** — a p50 value can mask two parallel processes.
   A histogram shape exposes them. Cheap to add next to the time-in-state heatmap.

### Anti-patterns to explicitly exclude

Documented in Phase 11, but flagged here for awareness:

- ❌ Lines of code / commit count as productivity metrics
- ❌ "Velocity" as a cross-team comparison
- ❌ LOC-weighted "impact" or "churn efficiency"
- ❌ Individual-ranking dashboards visible to managers by default
- ❌ Time-to-first-review as a KPI (produces rubber-stamp reviews)
- ❌ Raw per-developer sentiment scores (cross-cultural noise ~30%)

### Competitor landscape — DevPulse's lane

- **LinearB**: ship timelines, automation rules → skip "automation" for now, focus on insight depth
- **Swarmia**: research-backed curation, investment balance → adopt the discipline
- **Jellyfish**: Jira-first, epic-to-revenue mapping → NOT our lane
- **Pluralsight Flow (GitPrime)**: LOC-heavy, individual-focus → avoid this trap
- **Haystack**: DORA-first, metric-hygiene-explicit → align on this posture
- **DX**: survey-driven DevEx → future integration point, not v2

**DevPulse's defensible lane**: Linear-first (not Jira), team-health + friction signals that most
tools don't build (silos, ping-pong, blocked-chain depth), and TOC-style bottleneck drill-downs with
explicit anti-gaming framing.

## Phase plan — updated structure

```
01 Sync depth foundations         (expanded: SLA + triage + relations + project updates + botActor)
02 Linking upgrade + quality      (attachment-first GraphQL linker)
03 Linear Usage Health            (dashboard card, narrative framing)
04 Issue Conversations            (drill-down, correlation scatter)
05 Creator analytics              (stacked h2 sections on Dev Detail, not tab)
06 Flow analytics                 (history-driven, feature-flagged until enough data)
07 Bottleneck intelligence        (+ cycle-time stages, + ping-pong flag, + bus factor, + bimodal histogram)
08 Research synthesis             (THIS FILE)
09 GitHub PR timeline enrichment  (NEW — timelineItems: force push, review_requested, merge queue)
10 DORA v2 + AI-cohort split      (NEW — 2024 revision + Copilot cohort tagging)
11 Metrics governance             (NEW — guardrails, banners, permissions, outcome pairing)
```

Dependency graph (updated):
```
09 ──┐
01 ──┼──> 02 ──┬──> 03
     │         ├──> 04
     │         └──> 05
     ├──> 06
     ├──> 07 <──┘  (Phase 09 enriches timeline data used by 07 cycle-time-stages)
     └──> 10 ──> 11 (governance applies to all metric surfaces)
```

## Rate-limit budget notes (for future ops planning)

Documented for Phase 01 + 09 implementers:

- **Linear** API key: 3,000,000 complexity points/hr. Per-issue expansion (100 comments + 100
  history events + 50 attachments + 50 relations) ≈ 35 points per issue. 588 issues × 35 = ~20k
  points = 0.7% of hourly budget. Comfortable.
- **Linear** OAuth: 2,000,000 complexity points/hr. Still fine at 1% of budget.
- **GitHub** GraphQL: 5,000 points/hr per installation. Timeline-items for 50 PRs per query ≈ 8
  points. Typical DevPulse sync touches ~200-500 PRs → 80 points total = 1.6% of hourly budget.
- **GitHub** REST: 5,000-15,000/hr depending on installation scope. Use REST only for
  CODEOWNERS errors, workflow jobs/timing, webhook deltas.

## Deferred post-epic items (not in v2 scope, flagged for future)

- Linear webhook receiver for near-real-time sync (HMAC-SHA256 verification, replay-window)
- Sentiment analysis on PR review comments as team-aggregate opt-in AI feature
- Team Topologies auto-classification (requires care — high misread risk)
- SPACE Satisfaction survey hook (requires UI survey module)
- DevEx framework survey integration (survey-first tool)
- Linear Initiatives/Roadmaps sync (Phase 01 already prepares the schema surface; can follow-up
  if teams use them)
- Bimodal distribution detection as a first-class alert type (vs. just a chart)

## Sources (highlights)

See individual research outputs for full citations. Highlights:

- Linear: https://developers.linear.app/, https://linear.app/developers/rate-limiting,
  https://linear.app/developers/webhooks, https://linear.app/docs/insights
- GitHub: https://docs.github.com/en/rest/issues/timeline,
  https://docs.github.com/en/graphql/reference/unions,
  https://docs.github.com/en/rest/repos/rules,
  https://docs.github.com/en/graphql/overview/resource-limitations
- DORA: https://dora.dev/research/2024/dora-report/
- SPACE: https://queue.acm.org/detail.cfm?id=3454124
- Flow Framework: https://flowframework.org/
- Team Topologies: https://teamtopologies.com/key-concepts
- Goodhart's Law applied: https://jellyfish.co/blog/goodharts-law-in-software-engineering...
- AI cohort effects: https://jellyfish.co/blog/2025-ai-metrics-in-review/,
  https://github.blog/changelog/2026-04-08-copilot-reviewed-pull-request-merge-metrics-now-in-the-usage-metrics-api/
