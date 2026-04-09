# Phase 5: Collaboration and Workload Enrichment

> Priority: Medium | Effort: Medium | Impact: Medium
> Prerequisite: Phase 1 (bugfixes)
> Independent of: Phase 2, 3, 4
> Related: `backend/app/services/enhanced_collaboration.py`, `backend/app/services/stats.py`

## Status: Completed

## Problem

### Collaboration Gap

The collaboration scoring system computes 5 signals, weighted:
1. PR reviews (0.35)
2. Issue co-comments (0.20)
3. Co-repo authoring (0.15)
4. @mentions (0.15)
5. **Co-assignment on issues (0.15)** — uses GitHub `Issue.assignee_id` only

Signal 5 queries GitHub `issues` for co-assignment patterns. Teams that use Linear for issue tracking and assignment get zero signal from this component. Their collaboration scores are systematically 15% lower than they should be.

`ExternalIssue.assignee_developer_id` is a clean FK to `developers` — easier to join than the GitHub signal (which requires username-to-ID lookups).

### Workload Gap

The workload score formula is: `total_load = open_authored_prs + open_reviewing_prs + open_issues`. The `open_issues` component queries GitHub `Issue` only. When Linear is primary, open issue load should come from `ExternalIssue` where `status_category IN ('todo', 'in_progress')` and `assignee_developer_id = dev_id`.

Additionally, the workload model has no concept of sprint commitment. A developer with 3 open PRs and 12 sprint issues is significantly more loaded than one with 3 open PRs and 4 sprint issues. Sprint-scoped workload would be more accurate.

## Changes

### 5.1 Collaboration: Add Linear Co-Assignment Signal

**File:** `backend/app/services/enhanced_collaboration.py` (~line 178)

**Current signal 5 logic:** Queries `Issue.assignee_id` and `Issue.creator_github_username` to find developers working on the same GitHub issues.

**Enhancement:** When an active Linear integration exists, ALSO query `ExternalIssue`:
- Find pairs of developers assigned to issues in the same sprint (`ExternalIssue.sprint_id`)
- Find pairs where one developer created an issue and another is assigned (requires `creator_developer_id` from Phase 2, or use project-level co-membership as proxy)
- Weight: same 0.15 as current co-assignment signal

**Implementation approach:**

```python
async def _compute_co_assignment_signal(
    db: AsyncSession, dev_pairs: dict, date_from, date_to
) -> None:
    """Compute co-assignment signal from both GitHub and Linear issues."""
    
    # Existing GitHub co-assignment logic
    await _compute_github_co_assignment(db, dev_pairs, date_from, date_to)
    
    # Linear co-assignment (additive, not replacement)
    integration = await _get_active_linear_integration(db)
    if integration:
        await _compute_linear_co_assignment(db, dev_pairs, date_from, date_to)
```

For Linear co-assignment, the strongest signal is **sprint co-membership**: two developers assigned to issues in the same sprint are collaborating on the same body of work, even if they don't directly review each other's PRs.

**Query pattern:**
```sql
SELECT a.assignee_developer_id, b.assignee_developer_id, COUNT(DISTINCT a.sprint_id)
FROM external_issues a
JOIN external_issues b ON a.sprint_id = b.sprint_id 
  AND a.assignee_developer_id < b.assignee_developer_id
WHERE a.sprint_id IS NOT NULL
  AND a.assignee_developer_id IS NOT NULL
  AND b.assignee_developer_id IS NOT NULL
  AND a.updated_at >= :date_from
GROUP BY a.assignee_developer_id, b.assignee_developer_id
```

The `a.assignee_developer_id < b.assignee_developer_id` maintains canonical pair ordering (matches existing pattern in `developer_collaboration_scores`).

### 5.2 Workload: Add Linear Issue Load

**File:** `backend/app/services/stats.py`, workload computation

**Current formula:** `total_load = open_authored + open_reviewing + open_issues`

**Enhancement:** When Linear is the primary issue source, replace the `open_issues` component:

```python
source = await get_primary_issue_source(db)
if source == "linear":
    # Count active Linear issues (in current or upcoming sprint)
    open_issues = await db.scalar(
        select(func.count(ExternalIssue.id)).where(
            ExternalIssue.assignee_developer_id == dev_id,
            ExternalIssue.status_category.in_(["todo", "in_progress"]),
        )
    )
else:
    # Existing GitHub open issues count
    open_issues = ...  # current logic
```

### 5.3 Workload: Sprint Commitment Context (Optional Enhancement)

Add a `sprint_commitment` field to the workload response when Linear is active:

```python
{
    "developer_id": 42,
    "open_authored": 3,
    "open_reviewing": 2,
    "open_issues": 8,  # from Linear when primary
    "total_load": 13,
    "level": "overloaded",
    # New field:
    "sprint_commitment": {
        "sprint_name": "Sprint 24",
        "total_issues": 10,
        "completed": 6,
        "remaining": 4,
        "days_left": 5,
        "on_track": True  # remaining <= expected based on elapsed time
    }
}
```

This gives the workload page actionable sprint context. A developer may look "overloaded" by issue count but be on track for their sprint commitment.

**Frontend impact:** The Workload page (`/insights/workload`) can show a sprint progress indicator per developer when this data is available. Small addition to the existing workload cards.

### 5.4 Notification: Issue Linkage Alert Fix

**File:** `backend/app/services/notifications.py`

**Current bug:** The issue linkage notification evaluator uses `PullRequest.closes_issue_numbers` (GitHub "Closes #N" syntax). A PR linked to a Linear issue via `pr_external_issue_links` still triggers the "no issue linked" alert.

**Fix:** When Linear is the primary issue source, the linkage evaluator should check `pr_external_issue_links` instead of `closes_issue_numbers`. This is a direct consequence of Phase 2 (primary source branching) but lives in the notification evaluator.

```python
source = await get_primary_issue_source(db)
if source == "linear":
    # A PR is "linked" if it has any row in pr_external_issue_links
    linked_count = await db.scalar(
        select(func.count(distinct(PRExternalIssueLink.pull_request_id)))
        .where(...)
    )
else:
    # Existing: count PRs where closes_issue_numbers is not empty
    ...
```

## Dependencies

- Phase 2 (`creator_developer_id` on `ExternalIssue`) is nice-to-have for richer co-assignment signals but NOT required. Sprint co-membership works without it.
- Workload branching (5.2) requires `get_primary_issue_source()` — same pattern as Phase 2 but this is a simpler, independent use.

## Acceptance Criteria

- [ ] Collaboration scoring includes Linear sprint co-membership signal when Linear is active
- [ ] Collaboration scores are additive (GitHub signals + Linear signals, not replacement)
- [ ] Canonical pair ordering maintained for Linear co-assignment
- [ ] Workload `open_issues` uses `ExternalIssue` when Linear is primary
- [ ] Sprint commitment context included in workload response when available
- [ ] Issue linkage notification checks `pr_external_issue_links` when Linear is primary
- [ ] All existing collaboration/workload tests pass when Linear is not configured
- [ ] `recompute_collaboration_scores()` handles Linear data correctly

## Test Plan

- Unit test: Linear co-assignment signal computed correctly from sprint co-membership
- Unit test: collaboration score increases when Linear data adds co-assignment signal
- Unit test: workload `open_issues` queries `ExternalIssue` when Linear is primary
- Unit test: sprint commitment computed correctly from active sprint data
- Unit test: issue linkage evaluator uses `pr_external_issue_links` when Linear is primary
- Regression: collaboration scores unchanged when Linear not configured
- Regression: workload unchanged when GitHub is primary
