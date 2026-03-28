# Task P5-02: AI Usage Tracking & Cost Estimation API

## Phase
Phase 5 — Operational Excellence

## Status
completed

## Blocked By
- P5-01-ai-settings-backend

## Blocks
- P5-03-ai-settings-frontend

## Description
Build the usage aggregation and cost estimation endpoints that power the admin AI settings page. Includes per-feature usage breakdowns, daily usage timeseries, cost-estimate-before-running logic, and the feature status cards with human-readable descriptions and disable-impact text.

## Deliverables

### backend/app/services/ai_settings.py (extend from P5-01)

#### `get_feature_statuses(db, settings) -> list[AIFeatureStatus]`
Returns status card data for all 4 AI features. Each entry:

| Feature Key | Label | Description | Disabled Impact |
|-------------|-------|-------------|-----------------|
| `general_analysis` | "General Analysis" | "AI-powered communication, conflict, and sentiment analysis of PR reviews, issue comments, and team interactions." | "Admins cannot run communication, conflict, or sentiment analyses. All historical results remain accessible in the AI Analysis page." |
| `one_on_one_prep` | "1:1 Prep Brief" | "AI-generated structured meeting briefs with metric highlights, talking points, goal progress, and continuity from previous 1:1s." | "Admins must prepare 1:1 meeting notes manually. Developer stats, trends, benchmarks, and goal progress remain available without AI." |
| `team_health` | "Team Health Check" | "AI assessment of team velocity, workload balance, collaboration patterns, communication flags, and prioritized action items." | "No automated team health scoring. The Workload, Collaboration, and Benchmarks insight pages still provide all underlying data." |
| `work_categorization` | "Work Categorization" | "AI classification of PRs and issues into feature/bugfix/tech_debt/ops categories when label-based and title-regex rules cannot determine the type." | "The Investment page uses deterministic classification only (label mapping + title regex). Items that can't be auto-classified show as 'unknown' instead of being sent to AI." |

Per-feature metrics queries:
- For `general_analysis`, `one_on_one_prep`, `team_health`: query `ai_analyses` WHERE `analysis_type` matches AND `created_at >= month_start` AND `reused_from_id IS NULL` (don't count cache hits as usage). Sum `input_tokens + output_tokens`, count rows, compute cost, find max `created_at` for `last_used_at`.
- For `work_categorization`: query `ai_usage_log` WHERE `feature = 'work_categorization'` AND `created_at >= month_start`. Sum tokens, count rows, compute cost.

#### `get_daily_usage(db, settings, days=30) -> list[dict]`
Returns daily aggregation for the usage chart:
```python
[{
    "date": "2026-03-15",
    "tokens": 45230,
    "cost_usd": 0.18,
    "calls": 3,
    "by_feature": {
        "general_analysis": {"tokens": 12000, "calls": 1},
        "one_on_one_prep": {"tokens": 25000, "calls": 1},
        "work_categorization": {"tokens": 8230, "calls": 1},
    }
}]
```
Uses two queries (ai_analyses + ai_usage_log), grouped by `DATE(created_at)`, merged in Python.

#### `estimate_call_cost(db, feature, scope_type, scope_id, date_from, date_to) -> dict`
Lightweight pre-call cost estimation. Does NOT call Claude — just gathers data the same way the real call would, counts items, and estimates tokens:

| Feature | Estimation Logic |
|---------|-----------------|
| `general_analysis` | Call `_gather_scope_texts()`, count items × avg chars ÷ 4 for input tokens, assume 2000 output tokens |
| `one_on_one_prep` | Fixed estimate: 5000 input + 3000 output (based on typical context size) |
| `team_health` | Count team developers × 200 tokens + fixed 3000 base, assume 3000 output |
| `work_categorization` | Count unknown items × 10 tokens input, assume items × 5 output |

Returns:
```python
{
    "estimated_input_tokens": 5000,
    "estimated_output_tokens": 3000,
    "estimated_cost_usd": 0.06,
    "data_items": 45,  # items that would be sent
    "note": "Estimate based on current data volume"
}
```

### backend/app/api/ai_analysis.py (extend)

#### `GET /api/ai/usage`
```python
@router.get("/ai/usage", response_model=AIUsageSummary)
async def get_usage(
    days: int = Query(30, ge=1, le=365),
    db = Depends(get_db),
):
    """Usage breakdown by feature with daily timeseries."""
```

#### `POST /api/ai/estimate`
```python
@router.post("/ai/estimate")
async def estimate_cost(
    feature: str = Query(...),  # general_analysis, one_on_one_prep, team_health, work_categorization
    scope_type: str = Query(None),
    scope_id: str = Query(None),
    date_from: datetime = Query(None),
    date_to: datetime = Query(None),
    db = Depends(get_db),
):
    """Estimate token usage and cost for an AI call without executing it."""
```

### backend/app/schemas/schemas.py (extend)

```python
class AICostEstimate(BaseModel):
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    data_items: int
    note: str
```

## Testing

### backend/tests/unit/test_ai_usage.py (new)
- `test_feature_statuses_all_enabled` — returns 4 features with correct labels
- `test_feature_statuses_some_disabled` — `enabled` field reflects settings
- `test_feature_usage_counts_exclude_reused` — reused analyses not counted in usage tokens
- `test_daily_usage_aggregation` — correct daily grouping across both tables
- `test_daily_usage_empty_period` — days with no usage return zero entries (not omitted)
- `test_estimate_general_analysis` — returns plausible token estimate based on data volume
- `test_estimate_no_data` — returns zero estimate when no matching data
- `test_cost_computation_accuracy` — verify USD = (input × price/M) + (output × price/M)

## Files Created
- `backend/tests/unit/test_ai_usage.py` — 10 tests covering feature statuses, daily usage aggregation, cost computation

## Files Modified
- `backend/app/services/ai_settings.py` — Added `get_feature_statuses()`, `get_daily_usage()`, `get_usage_summary()`, `build_settings_response()`, `get_current_month_usage()`; fixed `cast(X, Date)` → `func.date(X)` for SQLite test compatibility
- `backend/app/api/ai_analysis.py` — Added `GET /api/ai/usage` and `POST /api/ai/estimate` endpoints

## Deviations from Spec
- `cast(created_at, Date)` replaced with `func.date(created_at)` in `get_daily_usage()` for SQLite compatibility in tests (both produce identical results in PostgreSQL)
