# Task AW-01: Backend — Accurate Dry-Run Cost Estimation & Repo Filtering

## Phase
AI Analysis Wizard

## Status
completed

## Blocked By
- None

## Blocks
- AW-02-backend-schedule-system
- AW-03-frontend-wizard
- AW-04-frontend-landing-schedules

## Description
Refactor the AI analysis backend to support accurate pre-run cost estimation via "dry-run" mode. Extract context-building logic from `run_one_on_one_prep()` and `run_team_health()` into reusable pure-data functions that can be called without invoking Claude. Add optional repo filtering to all data-gathering functions. Enhance the `AICostEstimate` response with character counts and budget headroom.

## Deliverables

### backend/app/services/ai_analysis.py

**Extract context builders (refactor, no new logic):**

1. `build_one_on_one_context(db, developer_id, date_from, date_to, repo_ids=None) -> dict`
   - Move lines 637-758 of `run_one_on_one_prep()` (the 8 data-gathering steps + context assembly) into this standalone async function
   - Returns the same `context` dict that gets passed to `_call_claude_and_store()`
   - `run_one_on_one_prep()` calls this function then passes result to `_call_claude_and_store()`
   - No behavioral change to `run_one_on_one_prep()` — pure refactor

2. `build_team_health_context(db, team, date_from, date_to, repo_ids=None) -> dict`
   - Move lines 867-1036 of `run_team_health()` (team stats, workload, collaboration, CR reviews, heated threads, goals + context assembly) into this standalone async function
   - Returns the same `context` dict
   - `run_team_health()` calls this function then passes result to `_call_claude_and_store()`
   - No behavioral change — pure refactor

**Add optional `repo_ids` parameter to data gathering:**

3. `_gather_developer_texts(db, developer_id, date_from, date_to, repo_ids=None)`
   - When `repo_ids` is provided (non-empty list), add `.where(PullRequest.repo_id.in_(repo_ids))` to the PR query
   - For reviews: join through `PullRequest` and filter on `PullRequest.repo_id.in_(repo_ids)`
   - For issue comments: join through `Issue` and filter on `Issue.repo_id.in_(repo_ids)`
   - When `repo_ids` is None or empty, no filter (current behavior)

4. `_gather_team_texts(db, team_name, date_from, date_to, repo_ids=None)`
   - Same pattern: filter PR/review queries by `PullRequest.repo_id.in_(repo_ids)` when provided

5. `_gather_scope_texts(db, scope_type, scope_id, date_from, date_to, repo_ids=None)`
   - Pass `repo_ids` through to `_gather_developer_texts` and `_gather_team_texts`
   - For `scope_type == "repo"`, `repo_ids` is ignored (already repo-scoped)

6. `build_one_on_one_context` repo filtering:
   - Filter PR query (step 4) with `PullRequest.repo_id.in_(repo_ids)` when provided
   - Filter review quality query (step 5) by joining through PullRequest
   - Stats/trends/benchmarks queries are NOT filtered by repo (they remain developer/team-wide)

7. `build_team_health_context` repo filtering:
   - Filter CR reviews query with `PullRequest.repo_id.in_(repo_ids)` when provided
   - Filter heated threads by joining Issue to repo filter
   - Stats/workload/collaboration are NOT repo-filtered (they remain team-wide)

**Propagate `repo_ids` through run functions:**

8. Add `repo_ids: list[int] | None = None` parameter to:
   - `run_analysis()` — pass to `_gather_scope_texts()`
   - `run_one_on_one_prep()` — pass to `build_one_on_one_context()`
   - `run_team_health()` — pass to `build_team_health_context()`

### backend/app/schemas/schemas.py

**Enhanced cost estimate response:**

9. Update `AICostEstimate`:
   ```python
   class AICostEstimate(BaseModel):
       estimated_input_tokens: int
       estimated_output_tokens: int
       estimated_cost_usd: float
       data_items: int
       character_count: int = 0          # total chars of serialized user content
       system_prompt_tokens: int = 0     # fixed overhead from system prompt
       remaining_budget_tokens: int = 0  # monthly budget - used tokens
       would_exceed_budget: bool = False # would this call bust the budget?
       note: str
   ```

**Enhanced request schemas (add repo_ids):**

10. Update `AIAnalyzeRequest`:
    ```python
    class AIAnalyzeRequest(BaseModel):
        analysis_type: AnalysisType
        scope_type: ScopeType
        scope_id: str
        date_from: datetime
        date_to: datetime
        repo_ids: list[int] | None = None  # optional repo filter
    ```

11. Update `OneOnOnePrepRequest`:
    ```python
    class OneOnOnePrepRequest(BaseModel):
        developer_id: int
        date_from: datetime
        date_to: datetime
        repo_ids: list[int] | None = None
    ```

12. Update `TeamHealthRequest`:
    ```python
    class TeamHealthRequest(BaseModel):
        team: str | None = None
        date_from: datetime
        date_to: datetime
        repo_ids: list[int] | None = None
    ```

### backend/app/services/ai_settings.py

**Rewrite `estimate_analysis_cost()`:**

13. Enhanced signature:
    ```python
    async def estimate_analysis_cost(
        db: AsyncSession,
        feature: str,
        scope_type: str | None = None,
        scope_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        repo_ids: list[int] | None = None,
    ) -> AICostEstimate:
    ```

14. For `general_analysis`: keep current approach (calls `_gather_scope_texts` with `repo_ids`), but also:
    - Compute `character_count = len(json.dumps(items).encode('utf-8'))`
    - Compute `system_prompt_tokens = len(SYSTEM_PROMPTS[analysis_type]) // 4` (import from ai_analysis)

15. For `one_on_one_prep`: call `build_one_on_one_context()` with `repo_ids`, then:
    - `serialized = json.dumps(context, default=str)`
    - `character_count = len(serialized.encode('utf-8'))`
    - `est_input = character_count // 4 + system_prompt_tokens`
    - `system_prompt_tokens = len(ONE_ON_ONE_SYSTEM_PROMPT) // 4`
    - `est_output = 3000` (output size is model-determined, keep heuristic)

16. For `team_health`: call `build_team_health_context()` with `repo_ids`, same pattern as above
    - `system_prompt_tokens = len(TEAM_HEALTH_SYSTEM_PROMPT) // 4`

17. For all features, after computing token estimate:
    - Call `check_budget(db, ai_settings)` to get `remaining_budget_tokens`
    - Set `would_exceed_budget = (est_input + est_output) > remaining_budget_tokens` (if budget is set)

### backend/app/api/ai_analysis.py

**Update endpoints to pass `repo_ids`:**

18. `POST /ai/analyze` — pass `request.repo_ids` to `run_analysis()`
19. `POST /ai/one-on-one-prep` — pass `request.repo_ids` to `run_one_on_one_prep()`
20. `POST /ai/team-health` — pass `request.repo_ids` to `run_team_health()`

**Update estimate endpoint:**

21. `POST /ai/estimate` — add `repo_ids` query parameter:
    ```python
    @router.post("/ai/estimate", response_model=AICostEstimate)
    async def estimate_cost(
        feature: str = Query(...),
        scope_type: str | None = Query(None),
        scope_id: str | None = Query(None),
        date_from: str | None = Query(None),
        date_to: str | None = Query(None),
        repo_ids: str | None = Query(None),  # comma-separated IDs
        db: AsyncSession = Depends(get_db),
    ):
        parsed_repo_ids = [int(x) for x in repo_ids.split(',')] if repo_ids else None
        return await estimate_analysis_cost(
            db, feature, scope_type, scope_id, date_from, date_to, parsed_repo_ids,
        )
    ```

### backend/tests/

22. Test `build_one_on_one_context()` returns expected dict structure (keys: developer, period, stats, trends, benchmarks, prs, review_quality, goals, previous_brief, issue_creator_stats)
23. Test `build_team_health_context()` returns expected dict structure (keys: team, period, team_stats, benchmarks, workload, collaboration, changes_requested_reviews, heated_threads, team_goals)
24. Test `estimate_analysis_cost()` with `feature="one_on_one_prep"` returns non-zero `character_count` and `system_prompt_tokens`
25. Test `estimate_analysis_cost()` with `feature="team_health"` returns non-zero `character_count`
26. Test repo_ids filtering: create PRs in 2 repos, call `_gather_developer_texts()` with repo_ids=[repo1_id], verify only repo1 items returned
27. Test `would_exceed_budget=True` when estimated tokens exceed remaining budget
