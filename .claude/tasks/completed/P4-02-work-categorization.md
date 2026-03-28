# Task P4-02: Work Categorization (Feature / Bug / Tech-Debt / Ops)

## Phase
Phase 4 — Make It Best-in-Class

## Status
completed

## Blocked By
- P2-05-pr-metadata-capture
- P3-03-issue-quality-scoring

## Blocks
None

## Description
Categorize engineering work into Feature, Bug Fix, Tech Debt, and Operational/Maintenance to answer the #1 question managers ask: "Where is our engineering time actually going?" This uses existing labels from issues and PRs, with optional AI-assisted classification for unlabeled items.

## Deliverables

### Work category taxonomy
```
feature    — new functionality, user-facing changes
bugfix     — fixing broken behavior
tech_debt  — refactoring, dependency updates, code cleanup
ops        — CI/CD, infra, monitoring, docs, tooling
unknown    — unclassifiable
```

### backend/app/services/categorization.py (new)

**Label-based classification** (primary):
Map common GitHub labels to categories:
```python
LABEL_MAP = {
    "feature": "feature", "enhancement": "feature", "new": "feature",
    "bug": "bugfix", "fix": "bugfix", "hotfix": "bugfix",
    "tech-debt": "tech_debt", "refactor": "tech_debt", "cleanup": "tech_debt", "chore": "tech_debt",
    "infra": "ops", "ci": "ops", "docs": "ops", "documentation": "ops", "ops": "ops",
}
```

Function: `classify_work_item(labels: list[str], title: str, body: str) -> str`
1. Check labels against `LABEL_MAP` — first match wins
2. If no label match, check title keywords (e.g., "fix", "bug", "refactor", "update deps")
3. If still unknown and AI is enabled, use Claude for classification (optional, configurable)
4. Default: "unknown"

### backend/app/services/stats.py (extend)
New function: `async def get_work_allocation(session, date_from, date_to, team=None)`

Returns:
- Per-category: `{category: {pr_count, additions, deletions, pct_of_total}}`
- Per-developer breakdown: `{developer_name: {feature: N, bugfix: N, tech_debt: N, ops: N}}`
- Trend: allocation per period (weekly/monthly) for investment tracking

### backend/app/schemas/schemas.py (extend)
```python
class WorkAllocation(BaseModel):
    category: str
    pr_count: int
    total_additions: int
    total_deletions: int
    pct_of_total: float

class WorkAllocationResponse(BaseModel):
    allocations: list[WorkAllocation]
    by_developer: dict[str, dict[str, int]]
    by_period: list[dict]  # [{period, feature, bugfix, tech_debt, ops}]
```

### backend/app/api/stats.py (extend)
New route: `GET /api/stats/work-allocation`
- Query params: `date_from`, `date_to`, `team`
- Returns `WorkAllocationResponse`

### Frontend
- Add "Investment Allocation" section to Insights
- Pie/donut chart showing category distribution
- Stacked bar chart showing allocation over time (weeks/months)
- Per-developer breakdown table
