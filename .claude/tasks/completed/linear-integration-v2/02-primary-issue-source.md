# Phase 2: Make Primary Issue Source Toggle Functional

> Priority: High | Effort: Large | Impact: High
> Prerequisite: Phase 1 (bugfixes)
> Blocks: Phase 7 (cross-linking UX)

## Status: Completed

## Problem

The `is_primary_issue_source` flag exists in `integration_config`, is exposed via `GET /integrations/issue-source` and `PATCH /integrations/{id}/primary`, and has a toggle in the IntegrationSettings UI. But `get_primary_issue_source()` is never called by any service outside `linear_sync.py` itself. The entire stats, benchmarks, and notification system queries only the GitHub `issues` table regardless of the toggle state.

This is the single highest-impact change in the v2 roadmap. When a team sets Linear as primary, their real issue data should flow through every feature.

## What Needs to Branch

When `primary_issue_source == "linear"`, the following must query `external_issues` instead of `issues`:

### 2.1 Developer Stats (`backend/app/services/stats.py`)

**Function: `get_developer_stats()`** (~line 287)
- `issues_assigned` → count `ExternalIssue` where `assignee_developer_id = dev_id`
- `issues_closed` → count `ExternalIssue` where `assignee_developer_id = dev_id` AND `status_category = 'done'`
- `avg_time_to_close_issue_hours` → avg `ExternalIssue.cycle_time_s / 3600` (Linear's cycle time replaces GitHub's `time_to_close_s`)

**Function: `get_activity_summary()`** (~line 460)
- `issues_created` → not directly available (Linear doesn't track creator the same way). Options:
  - (a) Skip this metric when Linear is primary (issues_created is GitHub-specific)
  - (b) Add a `creator_developer_id` FK to `external_issues` during sync (requires storing who created the Linear issue)
- `issues_assigned` → count from `ExternalIssue.assignee_developer_id`

**Recommended approach:** Add `creator_developer_id` to `external_issues` model + sync. Linear's issue has a `creator` field in the GraphQL API. This keeps feature parity with GitHub.

**Function: `get_team_stats()`** (~line 617)
- `total_issues_closed` → count closed `ExternalIssue` for developers on the team

**Function: `get_repo_stats()`** (~line 698)
- `total_issues` / `total_issues_closed` → These are repo-scoped and don't have a direct Linear equivalent (Linear issues aren't per-repo). When Linear is primary:
  - Option A: Show issue count as "N/A" for repo stats
  - Option B: Count linked issues (via `pr_external_issue_links` → PRs in that repo)
  - **Recommended: Option B** — gives a meaningful "issues addressed by this repo" count

### 2.2 Issue Linkage Stats (`backend/app/services/stats.py`)

**Function: `get_issue_linkage_stats()`** (~line 2257)
Currently uses `PullRequest.closes_issue_numbers` (GitHub "Closes #N" syntax).

When Linear is primary, switch to `pr_external_issue_links`:
- A PR is "linked" if it has at least one row in `pr_external_issue_links`
- Total PRs and linked PRs counted the same way
- This is strictly better data — `pr_external_issue_links` captures title/branch/body references, not just closing keywords

**Function: `get_issue_linkage_by_developer()`** (~line 2371)
Same switch — use `pr_external_issue_links` join instead of `closes_issue_numbers` JSON.

**Benchmark metric: `issue_linkage_rate`** in `_compute_per_developer_metrics()`
Same switch for the benchmark computation.

### 2.3 Issue Quality Stats (`backend/app/services/stats.py`)

**Function: `get_issue_quality_stats()`** (~line 2463)
Currently scores GitHub issues on: description length, checklist presence, label count, comment count.

When Linear is primary, query `ExternalIssue`:
- `description_length` → already stored on `ExternalIssue`
- Labels → `ExternalIssue.labels` JSONB
- Comments → not currently synced from Linear (gap — see below)
- Checklists → not standard in Linear (skip or adapt)

**Gap: Linear issue comments are not synced.** The current `external_issues` model doesn't have a comments table equivalent to `issue_comments`. For issue quality scoring, `description_length` and `labels` are sufficient for a v1. Comment count can be added when Linear comments are synced (future phase).

### 2.4 Issue Creator Stats (`backend/app/services/stats.py`)

**Function: `get_issue_creator_stats()`**
When Linear is primary, query `ExternalIssue` grouped by `creator_developer_id` (requires the new FK from 2.1).

### 2.5 Work Categorization (`backend/app/services/work_categories.py`)

**Function: `classify_work_item_with_rules()`**
Currently classifies GitHub issues by: labels, title regex, prefix, issue_type.

When Linear is primary, the same classification pipeline should run on `ExternalIssue`:
- Labels → `ExternalIssue.labels` JSONB (same format)
- Title regex/prefix → `ExternalIssue.title`
- Issue type → `ExternalIssue.issue_type` (already populated: "issue", "bug", "feature", etc.)
- AI classification → same prompt, different source data

**Implementation:** Add `work_category` and `work_category_source` columns to `ExternalIssue` model. Run classification at sync time (same as GitHub issues). The classification function is already pure — it just needs to be called with Linear issue data.

### 2.6 Work Allocation (`backend/app/services/work_category.py`)

**Function: `get_work_allocation()`**
When Linear is primary, include `ExternalIssue` in the allocation breakdown (feature/bugfix/tech_debt/ops/unknown donut chart).

**Cross-reference classification:** Currently PRs inherit category from linked GitHub issues via `closes_issue_numbers`. When Linear is primary, PRs should inherit from linked `ExternalIssue` via `pr_external_issue_links`. The join path is: `PullRequest → PRExternalIssueLink → ExternalIssue.work_category`.

## Implementation Strategy

### Helper Pattern

Create a shared helper that abstracts the branching:

```python
# In stats.py or a new utils module
async def _issue_source_context(db: AsyncSession) -> IssueSourceContext:
    """Returns table references and join paths based on primary issue source."""
    source = await get_primary_issue_source(db)
    if source == "linear":
        return IssueSourceContext(
            issue_model=ExternalIssue,
            assignee_col=ExternalIssue.assignee_developer_id,
            status_done_filter=ExternalIssue.status_category == "done",
            close_time_col=ExternalIssue.cycle_time_s,
            linkage_join=PRExternalIssueLink,
            # ... etc
        )
    else:
        return IssueSourceContext(
            issue_model=Issue,
            assignee_col=Issue.assignee_id,
            # ... etc
        )
```

This avoids duplicating every query. Each stats function calls `_issue_source_context()` once and uses the returned model/column references.

**However** — be pragmatic. If the branching is simpler as two query blocks with an `if/else`, do that. Don't over-abstract for the sake of it. Some functions (like issue quality) have fundamentally different logic per source and can't share a query template.

### Migration

Add to `ExternalIssue` model:
- `creator_developer_id` (FK to developers, nullable) — populated from Linear's `issue.creator.email` → `developer_identity_map` lookup
- `work_category` (String, nullable) — classification result
- `work_category_source` (String, nullable) — classification provenance

Update `ISSUES_QUERY` in `linear_sync.py` to fetch `creator { id email displayName }`.

### What Does NOT Switch

These always use GitHub data regardless of primary source:
- PR metrics (PRs, merge time, cycle time) — Linear doesn't have PRs
- Review metrics (quality, throughput) — GitHub only
- DORA metrics (deployments) — GitHub only
- Collaboration PR/review signals — GitHub only
- Sprint/velocity/triage/estimation — always Linear (dedicated pages)

## Acceptance Criteria

- [ ] `get_primary_issue_source()` is called at the top of every issue-related stats function
- [ ] When Linear is primary: developer stats show Linear issue counts and cycle times
- [ ] When Linear is primary: issue linkage uses `pr_external_issue_links` table
- [ ] When Linear is primary: work categorization runs on `ExternalIssue` data
- [ ] When Linear is primary: work allocation includes Linear issues
- [ ] When GitHub is primary (default): all behavior is unchanged
- [ ] `ExternalIssue` has `creator_developer_id`, `work_category`, `work_category_source` columns
- [ ] Linear issue creator is mapped during sync
- [ ] All existing tests pass (GitHub-primary path unchanged)
- [ ] New tests cover Linear-primary path for each branched function

## Test Plan

- Unit test: `_issue_source_context()` returns correct models for each source
- Unit test: `get_developer_stats()` with Linear primary returns `ExternalIssue` counts
- Unit test: `get_issue_linkage_stats()` with Linear primary uses `pr_external_issue_links`
- Unit test: `classify_work_item_with_rules()` works with Linear issue data
- Integration test: toggle primary source and verify stats API responses change
- Integration test: work allocation endpoint reflects Linear issues when primary
- Regression test: all stats endpoints return same results when GitHub is primary (no behavioral change)
