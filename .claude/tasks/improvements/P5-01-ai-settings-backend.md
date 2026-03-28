# Task P5-01: AI Settings & Cost Controls — Backend

## Phase
Phase 5 — Operational Excellence

## Status
completed

## Blocked By
None

## Blocks
- P5-02-ai-usage-tracking
- P5-03-ai-settings-frontend

## Description
Add a singleton `ai_settings` table and service layer that provides per-feature toggles, a monthly token budget with hard cutoff, configurable Anthropic pricing, and a cooldown-based deduplication window. Integrate guard checks into all 4 existing AI call sites so they respect toggles, budget, and cooldown before calling Claude.

## Deliverables

### backend/migrations/versions/013_add_ai_settings.py (new)
Alembic migration creating the `ai_settings` table:

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `id` | Integer PK | — | Always 1 (singleton) |
| `ai_enabled` | Boolean | `True` | Master on/off switch |
| `feature_general_analysis` | Boolean | `True` | Toggle for communication/conflict/sentiment |
| `feature_one_on_one_prep` | Boolean | `True` | Toggle for 1:1 prep briefs |
| `feature_team_health` | Boolean | `True` | Toggle for team health checks |
| `feature_work_categorization` | Boolean | `True` | Toggle for AI batch classification |
| `monthly_token_budget` | Integer, nullable | `None` | `None` = unlimited. Token count cap per calendar month. |
| `budget_warning_threshold` | Float | `0.8` | Fraction (0-1) at which to warn |
| `input_token_price_per_million` | Float | `3.0` | Default Sonnet input pricing (USD) |
| `output_token_price_per_million` | Float | `15.0` | Default Sonnet output pricing (USD) |
| `pricing_updated_at` | DateTime(tz), nullable | `None` | When pricing was last reviewed/updated |
| `cooldown_minutes` | Integer | `30` | Dedup window — recent analysis reuse |
| `updated_at` | DateTime(tz) | `now()` | Last settings change |
| `updated_by` | String(255), nullable | `None` | Admin username who last changed settings |

Insert default row with `id=1` in the `upgrade()` function via `op.execute(INSERT ...)`.

Also add columns to `ai_analyses` table:
- `input_tokens` Integer, nullable — split from existing `tokens_used`
- `output_tokens` Integer, nullable — split from existing `tokens_used`
- `estimated_cost_usd` Float, nullable — computed at write time from pricing
- `reused_from_id` Integer, nullable, FK to `ai_analyses.id` — set when returning a cached result

### backend/app/models/models.py
Add `AISettings` ORM model:
```python
class AISettings(Base):
    __tablename__ = "ai_settings"
    id, ai_enabled, feature_general_analysis, feature_one_on_one_prep,
    feature_team_health, feature_work_categorization,
    monthly_token_budget, budget_warning_threshold,
    input_token_price_per_million, output_token_price_per_million,
    pricing_updated_at, cooldown_minutes, updated_at, updated_by
```

Add to `AIAnalysis` model:
- `input_tokens: Mapped[int | None]`
- `output_tokens: Mapped[int | None]`
- `estimated_cost_usd: Mapped[float | None]`
- `reused_from_id: Mapped[int | None]` (ForeignKey to self)

### backend/app/schemas/schemas.py
New schemas:

```python
class AISettingsResponse(BaseModel):
    """Full settings + current usage summary for the admin panel."""
    model_config = ConfigDict(from_attributes=True)
    ai_enabled: bool
    feature_general_analysis: bool
    feature_one_on_one_prep: bool
    feature_team_health: bool
    feature_work_categorization: bool
    monthly_token_budget: int | None
    budget_warning_threshold: float
    input_token_price_per_million: float
    output_token_price_per_million: float
    pricing_updated_at: datetime | None
    cooldown_minutes: int
    updated_at: datetime
    updated_by: str | None
    # Computed fields (not from DB — populated by service)
    api_key_configured: bool  # True if ANTHROPIC_API_KEY is set
    current_month_tokens: int  # sum of tokens_used this calendar month
    current_month_cost_usd: float  # estimated cost this month
    budget_pct_used: float | None  # current_month_tokens / monthly_token_budget

class AISettingsUpdate(BaseModel):
    """Partial update — all fields optional."""
    ai_enabled: bool | None = None
    feature_general_analysis: bool | None = None
    feature_one_on_one_prep: bool | None = None
    feature_team_health: bool | None = None
    feature_work_categorization: bool | None = None
    monthly_token_budget: int | None = None  # pass 0 to clear (set to None)
    budget_warning_threshold: float | None = None
    input_token_price_per_million: float | None = None
    output_token_price_per_million: float | None = None
    cooldown_minutes: int | None = None

class AIFeatureStatus(BaseModel):
    """Per-feature status for the admin panel."""
    feature: str  # "general_analysis", "one_on_one_prep", etc.
    enabled: bool
    label: str  # Human-readable name
    description: str  # What it does
    disabled_impact: str  # What happens when turned off
    tokens_this_month: int
    cost_this_month_usd: float
    call_count_this_month: int
    last_used_at: datetime | None

class AIUsageSummary(BaseModel):
    """Aggregate usage data for the admin panel."""
    period_start: datetime
    period_end: datetime
    total_tokens: int
    total_cost_usd: float
    budget_limit: int | None
    budget_pct_used: float | None
    features: list[AIFeatureStatus]
    daily_usage: list[dict]  # [{date, tokens, cost, calls}]
```

Update `AIAnalysisResponse`:
- Add `input_tokens: int | None`
- Add `output_tokens: int | None`
- Add `estimated_cost_usd: float | None`
- Add `reused: bool = False` (computed: `reused_from_id is not None`)

### backend/app/services/ai_settings.py (new)
Core service functions:

```python
async def get_ai_settings(db: AsyncSession) -> AISettings:
    """Get singleton settings row. Creates default if missing."""

async def update_ai_settings(
    db: AsyncSession, updates: AISettingsUpdate, updated_by: str
) -> AISettings:
    """Partial update of settings. Sets updated_at and updated_by.
    If pricing fields changed, also set pricing_updated_at."""

async def check_feature_enabled(db: AsyncSession, feature_name: str) -> AISettings:
    """Returns settings if feature is enabled.
    Raises HTTPException(403) if master switch is off OR specific feature is off.
    Error detail includes feature name + human-readable message."""

async def check_budget(db: AsyncSession, settings: AISettings) -> dict:
    """Returns {tokens_used, budget_limit, pct_used, over_budget: bool}.
    Queries sum of tokens_used from ai_analyses + ai_usage_log
    WHERE created_at >= first day of current month (UTC).
    If monthly_token_budget is None, over_budget is always False."""

async def find_recent_analysis(
    db: AsyncSession, analysis_type: str, scope_type: str,
    scope_id: str, cooldown_minutes: int
) -> AIAnalysis | None:
    """Find most recent analysis matching type+scope within cooldown window.
    Returns None if no match or cooldown expired."""

async def get_usage_summary(db: AsyncSession, settings: AISettings) -> AIUsageSummary:
    """Aggregate usage for current month, broken down by feature and day.
    Queries ai_analyses grouped by analysis_type + date.
    Queries ai_usage_log for work_categorization usage.
    Computes cost using settings pricing."""

def compute_cost(input_tokens: int, output_tokens: int, settings: AISettings) -> float:
    """Calculate estimated cost in USD from token counts and pricing config."""
```

### backend/app/services/ai_analysis.py (modify)
Integrate guards into all 3 call sites:

**`run_analysis()`** — add at top:
```python
ai_settings = await check_feature_enabled(db, "general_analysis")
budget_info = await check_budget(db, ai_settings)
if budget_info["over_budget"]:
    raise HTTPException(429, detail="Monthly AI token budget exceeded")
# Dedup check (unless force=True)
if not force:
    recent = await find_recent_analysis(db, analysis_type, scope_type, scope_id, ai_settings.cooldown_minutes)
    if recent:
        return recent  # frontend detects via reused_from_id
```
After Claude response, store split tokens + cost:
```python
input_tokens = response.usage.input_tokens
output_tokens = response.usage.output_tokens
estimated_cost = compute_cost(input_tokens, output_tokens, ai_settings)
```
Add `force: bool = False` parameter.

**`run_one_on_one_prep()`** — same pattern with `feature_name="one_on_one_prep"`. Dedup key: `analysis_type="one_on_one_prep"`, `scope_type="developer"`, `scope_id=str(developer_id)`.

**`run_team_health()`** — same pattern with `feature_name="team_health"`. Dedup key: `analysis_type="team_health"`, `scope_type="team"`, `scope_id=team or "all"`.

**`_call_claude_and_store()`** — update to accept and store `input_tokens`, `output_tokens`, `estimated_cost_usd` separately (keep `tokens_used` as sum for backward compat).

### backend/app/services/work_category.py (modify)
In `ai_classify_batch()`:
- Add guard: `ai_settings = await check_feature_enabled(db, "work_categorization")`
- Add budget check before calling Claude
- After Claude response, log usage to `ai_usage_log` table:
  ```python
  log = AIUsageLog(feature="work_categorization", input_tokens=..., output_tokens=..., items_classified=len(results), created_at=now)
  db.add(log)
  ```
- This requires passing `db` session into `ai_classify_batch()` (currently it doesn't receive one — will need signature change)

Note: `ai_classify_batch` is called from `get_work_allocation()` which already has `db`. Thread it through.

### backend/app/models/models.py — AIUsageLog model
```python
class AIUsageLog(Base):
    __tablename__ = "ai_usage_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    feature: Mapped[str] = mapped_column(String(50))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    items_classified: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
```

Include `ai_usage_log` in the same migration (013).

### backend/app/api/ai_analysis.py (modify)
Add new endpoints:

```python
@router.get("/ai/settings", response_model=AISettingsResponse)
async def get_settings(db = Depends(get_db)):
    """Get current AI settings + usage summary."""

@router.patch("/ai/settings", response_model=AISettingsResponse)
async def update_settings(
    updates: AISettingsUpdate,
    db = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
):
    """Update AI settings (admin only). Returns updated settings + usage."""
```

Update `trigger_analysis()` to pass `force` query param:
```python
async def trigger_analysis(request: AIAnalyzeRequest, force: bool = Query(False), ...):
```

Update `AIAnalysisResponse` serialization — add `reused` computed field.

### backend/app/api/stats.py (modify)
The `work_allocation` endpoint already passes `use_ai` to the service. The guard is added inside `ai_classify_batch()` so no route changes needed. But the service function signature for `ai_classify_batch` changes to accept `db`.

## Testing

### backend/tests/unit/test_ai_settings.py (new)
- `test_get_default_settings` — creates default row, verifies all defaults
- `test_update_settings_partial` — update only `ai_enabled`, others unchanged
- `test_update_pricing_sets_pricing_updated_at` — changing price fields auto-sets timestamp
- `test_check_feature_enabled_master_off` — raises 403 when `ai_enabled=False`
- `test_check_feature_enabled_feature_off` — raises 403 when specific feature disabled
- `test_check_feature_enabled_both_on` — returns settings when both enabled
- `test_check_budget_unlimited` — `monthly_token_budget=None` → never over budget
- `test_check_budget_under_limit` — returns correct pct, not over
- `test_check_budget_over_limit` — returns `over_budget=True`
- `test_find_recent_analysis_within_cooldown` — returns recent match
- `test_find_recent_analysis_expired` — returns None when older than cooldown
- `test_find_recent_analysis_different_scope` — returns None for different scope
- `test_compute_cost` — correct USD calculation from token counts + pricing
- `test_usage_summary_aggregation` — correct per-feature + daily breakdown

### backend/tests/unit/test_ai_guards.py (new)
- `test_run_analysis_feature_disabled` — returns 403
- `test_run_analysis_over_budget` — returns 429
- `test_run_analysis_dedup_returns_cached` — returns existing analysis with `reused_from_id`
- `test_run_analysis_force_bypasses_dedup` — `force=True` always calls Claude
- `test_work_categorization_disabled` — `ai_classify_batch` returns `{}` when feature off
- `test_work_categorization_over_budget` — returns `{}` when over budget
- `test_work_categorization_logs_usage` — creates `ai_usage_log` entry after call

## Files Created
- `backend/migrations/versions/013_add_ai_settings.py`
- `backend/app/services/ai_settings.py`
- `backend/tests/unit/test_ai_settings.py`
- `backend/tests/unit/test_ai_guards.py`

## Files Modified
- `backend/app/models/models.py` — Added `AISettings` and `AIUsageLog` models; added `input_tokens`, `output_tokens`, `estimated_cost_usd`, `reused_from_id` to `AIAnalysis`
- `backend/app/schemas/schemas.py` — Added `AISettingsResponse`, `AISettingsUpdate`, `AIFeatureStatus`, `AIUsageSummary`, `AICostEstimate`, `DailyUsage` schemas; updated `AIAnalysisResponse` with cost/reused fields
- `backend/app/services/ai_analysis.py` — Integrated guards (check_feature_enabled, check_budget, find_recent_analysis) into `run_analysis()`, `run_one_on_one_prep()`, `run_team_health()`; added `force` param; split token tracking + cost computation
- `backend/app/services/work_category.py` — Added guard checks and usage logging to `ai_classify_batch()`
- `backend/app/api/ai_analysis.py` — Added `GET/PATCH /ai/settings`, `GET /ai/usage`, `POST /ai/estimate` endpoints; added `force` query param to all AI trigger endpoints
