# Phase 3: AI Context Enrichment with Linear Data

> Priority: High | Effort: Medium | Impact: High
> Prerequisite: Phase 1 (bugfixes)
> Independent of: Phase 2 (primary issue source), Phase 4-5
> Related: `backend/app/services/ai_analysis.py`

## Status: Completed

## Problem

The AI context builders — `build_one_on_one_context()` and `build_team_health_context()` — provide Claude with GitHub PR/review data, benchmarks, goals, and collaboration metrics. But they include zero Linear data. When a team uses Linear for sprint planning, Claude has no visibility into:

- Whether a developer is meeting sprint commitments
- Sprint velocity trends (accelerating or decelerating)
- Scope creep patterns
- Triage backlog health
- Estimation accuracy
- Which sprint a developer's current work belongs to

This makes AI 1:1 prep briefs and team health checks significantly less useful for Linear-using teams. Claude literally doesn't know sprints exist.

## What to Add

### 3.1 One-on-One Prep Context (`build_one_on_one_context()`)

**File:** `backend/app/services/ai_analysis.py` (~line 602)

Add a `sprint_context` section when Linear is configured and the developer is identity-mapped:

```python
sprint_context = {
    "active_sprint": {
        "name": "Sprint 24",
        "days_remaining": 5,
        "issues_assigned": 8,
        "issues_completed": 5,
        "completion_pct": 62.5,
        "scope_added_mid_sprint": 2,
    },
    "recent_sprints": [
        {
            "name": "Sprint 23",
            "personal_completion_pct": 87.5,  # their issues done / their issues total
            "team_completion_pct": 78.0,
            "carried_over": 1,
        },
        # last 3 sprints
    ],
    "triage_stats": {
        "issues_in_triage_assigned_to_dev": 0,
        "avg_triage_duration_hours": 18.5,
    },
    "estimation_pattern": {
        "avg_estimate": 3.2,
        "completion_rate_by_size": {
            "small_1_2": 95,    # % of 1-2 point issues completed in sprint
            "medium_3_5": 80,
            "large_8_plus": 50,
        }
    }
}
```

**Data sources:**
- Active sprint: `ExternalSprint` where `state='active'`, joined to `ExternalIssue` where `assignee_developer_id = dev_id`
- Recent sprints: last 3 closed sprints, same developer filter
- Triage: `ExternalIssue` where `status_category='triage'` and `assignee_developer_id = dev_id`
- Estimation pattern: `ExternalIssue` grouped by estimate bucket, completion rate per bucket

**Guard:** Only include this section when:
1. An active Linear integration exists (`integration_config.status = 'active'`)
2. The developer has a mapping in `developer_identity_map`
3. There is at least one sprint with data

If any condition fails, omit the `sprint_context` key entirely (Claude handles missing context gracefully).

### 3.2 Team Health Context (`build_team_health_context()`)

**File:** `backend/app/services/ai_analysis.py` (~line 857)

Add a `planning_health` section when Linear is configured:

```python
planning_health = {
    "velocity_trend": {
        "direction": "declining",  # or "improving", "stable"
        "last_5_sprints": [45, 42, 38, 35, 32],
        "change_pct": -28.9,
    },
    "completion_rate": {
        "last_sprint": 72.0,
        "avg_last_5": 78.4,
        "trend": "declining",
    },
    "scope_creep": {
        "last_sprint_pct": 25.0,
        "avg_last_5_pct": 15.0,
        "trend": "worsening",
    },
    "triage_health": {
        "issues_in_triage": 12,
        "avg_triage_hours": 36.5,
        "p90_triage_hours": 96.0,
    },
    "estimation_accuracy": {
        "last_sprint_pct": 65.0,
        "trend": "stable",
    },
    "work_alignment_pct": 78.0,  # % of PRs linked to planned work
    "at_risk_projects": [
        {"name": "Auth Rewrite", "health": "at_risk", "progress_pct": 45, "days_to_target": 12}
    ]
}
```

**Data sources:** Reuse existing `sprint_stats.py` functions:
- `get_sprint_velocity()` → velocity trend
- `get_sprint_completion()` → completion rate
- `get_scope_creep()` → scope creep
- `get_triage_metrics()` → triage health
- `get_estimation_accuracy()` → estimation accuracy
- `get_work_alignment()` → work alignment
- Query `ExternalProject` where `health = 'at_risk'` or `health = 'off_track'`

### 3.3 System Prompt Updates

Update the system prompts for both analysis types to tell Claude about the sprint data:

**1:1 prep:** Add to the system prompt: "When sprint data is available, assess whether the developer is on track for current sprint commitments. Note patterns in estimation accuracy — are they consistently over-committing on large items? Flag if they have stale triage items or are carrying over work across sprints."

**Team health:** Add: "When planning health data is available, assess the team's planning discipline. Rising scope creep or declining velocity may indicate systemic planning issues, not just execution problems. Correlate PR delivery metrics with sprint completion — a team that merges fast but completes few sprint items may be doing a lot of unplanned work."

### 3.4 Cost Estimation Update

**Function: `estimate_analysis_cost()`** in `ai_settings.py`

The dry-run cost estimation builds the same context as the real analysis. If sprint context is added, the character count and token estimate will increase. No code change needed — the estimation already calls `build_one_on_one_context()` and `build_team_health_context()` directly, so the new data is automatically included in the estimate.

Verify that the budget warning thresholds are still reasonable with the added context. Sprint data adds roughly 500-2000 characters per analysis depending on sprint count.

## Implementation Notes

### New helper functions

Create focused data-gathering helpers in `ai_analysis.py` (or a new `ai_sprint_context.py` if cleaner):

```python
async def _gather_sprint_context_for_developer(
    db: AsyncSession, developer_id: int
) -> dict | None:
    """Build sprint context for 1:1 prep. Returns None if Linear not configured or dev not mapped."""

async def _gather_planning_health_context(
    db: AsyncSession, team: str | None = None, repo_ids: list[int] | None = None
) -> dict | None:
    """Build planning health context for team health. Returns None if Linear not configured."""
```

### Repo filtering

Both context builders accept optional `repo_ids` for scoping. Sprint data is not repo-scoped (sprints span repos), so `repo_ids` filtering doesn't apply to sprint context. However, work alignment (% PRs linked) CAN be repo-filtered — filter the PR side of the join.

## Acceptance Criteria

- [x] `build_one_on_one_context()` includes `sprint_context` when Linear is active and developer is mapped
- [x] `build_team_health_context()` includes `planning_health` when Linear is active
- [x] Context is omitted gracefully when Linear is not configured (no errors, no empty sections)
- [x] System prompts updated to guide Claude on sprint data interpretation
- [x] Cost estimation automatically reflects the larger context
- [x] All existing AI tests pass (context additions are additive, not breaking)

## Test Plan

- [x] Unit test: `gather_sprint_context_for_developer()` returns None when no Linear integration
- [x] Unit test: `gather_sprint_context_for_developer()` returns correct structure with mock sprint data
- [x] Unit test: `gather_planning_health_context()` aggregates sprint stats correctly
- [x] Unit test: `build_one_on_one_context()` includes sprint_context key when Linear active
- [x] Unit test: `build_team_health_context()` includes planning_health key when Linear active
- [x] Regression: `build_one_on_one_context()` output unchanged when Linear not configured

## Files Modified

- `backend/app/services/ai_analysis.py` — Added `gather_sprint_context_for_developer()`, `gather_planning_health_context()`, helper functions `_get_active_linear_integration()` and `_is_developer_mapped()`. Wired into `build_one_on_one_context()` and `build_team_health_context()`. Updated `ONE_ON_ONE_SYSTEM_PROMPT` and `TEAM_HEALTH_SYSTEM_PROMPT` with sprint-aware guidance.
- `backend/tests/service/test_ai_context_builders.py` — Added 15 tests: `TestGatherSprintContextForDeveloper` (7), `TestGatherPlanningHealthContext` (4), `TestOneOnOneContextWithSprint` (2), `TestTeamHealthContextWithPlanning` (2). Added fixtures for `linear_integration`, `dev_identity_map`, `active_sprint`, `closed_sprint`, `sprint_issues`.

## Implementation Notes

- Helper functions are named without underscore prefix (`gather_sprint_context_for_developer`, `gather_planning_health_context`) to allow direct import in tests.
- `gather_planning_health_context()` reuses existing `sprint_stats.py` functions — no duplicated query logic.
- Sprint context is additive: keys are only added to the context dict when data exists. No behavioral change when Linear is not configured.
- No new API endpoints or schema changes — context enrichment is internal to the AI analysis pipeline.
