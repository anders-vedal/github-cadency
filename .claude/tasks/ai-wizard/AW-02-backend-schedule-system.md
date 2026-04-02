# Task AW-02: Backend — AI Analysis Schedule System

## Phase
AI Analysis Wizard

## Status
completed

## Blocked By
- AW-01-backend-dry-run-estimation

## Blocks
- AW-04-frontend-landing-schedules

## Description
Add a multi-schedule system for recurring AI analyses. Each schedule is an independently configurable row with its own analysis type, scope, repo filter, time range, and cron frequency. Integrates with APScheduler for automated execution. Supports CRUD API + manual trigger.

## Deliverables

### backend/app/models/models.py

**New model `AIAnalysisSchedule`:**

1. Add after `AISettings` class:
   ```python
   class AIAnalysisSchedule(Base):
       __tablename__ = "ai_analysis_schedules"

       id: Mapped[int] = mapped_column(primary_key=True)
       name: Mapped[str] = mapped_column(String(255), nullable=False)
       # Analysis config
       analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
       # For general analysis: 'communication', 'conflict', 'sentiment'
       # For others: stored in analysis_type directly ('one_on_one_prep', 'team_health')
       general_type: Mapped[str | None] = mapped_column(String(50))
       scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
       scope_id: Mapped[str] = mapped_column(String(255), nullable=False)
       repo_ids: Mapped[list | None] = mapped_column(JSONB)  # optional repo filter
       time_range_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
       # Schedule config
       frequency: Mapped[str] = mapped_column(String(30), nullable=False)
       # 'daily', 'weekly', 'biweekly', 'monthly'
       day_of_week: Mapped[int | None] = mapped_column(Integer)
       # 0=Monday..6=Sunday, used for weekly/biweekly
       hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
       # Hour of day (0-23) to run
       minute: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
       # State
       is_enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
       last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
       last_run_analysis_id: Mapped[int | None] = mapped_column(Integer)
       last_run_status: Mapped[str | None] = mapped_column(String(30))
       # 'success', 'failed', 'budget_exceeded', 'feature_disabled'
       # Audit
       created_by: Mapped[str | None] = mapped_column(String(255))
       created_at: Mapped[datetime] = mapped_column(
           DateTime(timezone=True), default=datetime.utcnow, server_default=func.now()
       )
       updated_at: Mapped[datetime] = mapped_column(
           DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow,
           server_default=func.now()
       )
   ```

### backend/migrations/versions/

2. New Alembic migration `add_ai_analysis_schedules`:
   - Creates `ai_analysis_schedules` table with all columns above
   - Index on `is_enabled` for scheduler query
   - No data migration needed (new table)

### backend/app/schemas/schemas.py

**Schedule CRUD schemas:**

3. Add schemas:
   ```python
   class AIScheduleCreate(BaseModel):
       name: str = Field(max_length=255)
       analysis_type: str  # 'communication', 'conflict', 'sentiment', 'one_on_one_prep', 'team_health'
       general_type: str | None = None
       scope_type: str
       scope_id: str = Field(max_length=255)
       repo_ids: list[int] | None = None
       time_range_days: int = Field(default=30, ge=1, le=365)
       frequency: str  # 'daily', 'weekly', 'biweekly', 'monthly'
       day_of_week: int | None = Field(default=None, ge=0, le=6)
       hour: int = Field(default=8, ge=0, le=23)
       minute: int = Field(default=0, ge=0, le=59)

   class AIScheduleUpdate(BaseModel):
       name: str | None = Field(default=None, max_length=255)
       is_enabled: bool | None = None
       repo_ids: list[int] | None = None
       time_range_days: int | None = Field(default=None, ge=1, le=365)
       frequency: str | None = None
       day_of_week: int | None = Field(default=None, ge=0, le=6)
       hour: int | None = Field(default=None, ge=0, le=23)
       minute: int | None = Field(default=None, ge=0, le=59)
       # analysis_type/scope not updatable — delete and recreate

   class AIScheduleResponse(BaseModel):
       model_config = ConfigDict(from_attributes=True)

       id: int
       name: str
       analysis_type: str
       general_type: str | None
       scope_type: str
       scope_id: str
       repo_ids: list[int] | None
       time_range_days: int
       frequency: str
       day_of_week: int | None
       hour: int
       minute: int
       is_enabled: bool
       last_run_at: datetime | None
       last_run_analysis_id: int | None
       last_run_status: str | None
       created_by: str | None
       created_at: datetime
       updated_at: datetime
       # Computed fields for display
       next_run_description: str | None = None  # human-readable, e.g. "Weekly on Monday at 8:00 AM"
   ```

### backend/app/services/ai_schedules.py (new file)

**Schedule CRUD + execution:**

4. `list_schedules(db) -> list[AIAnalysisSchedule]`
   - `SELECT * FROM ai_analysis_schedules ORDER BY created_at DESC`

5. `create_schedule(db, data: AIScheduleCreate, created_by: str) -> AIAnalysisSchedule`
   - Validate analysis_type is one of: communication, conflict, sentiment, one_on_one_prep, team_health
   - Validate scope_type matches analysis_type expectations (conflict requires team, etc.)
   - Validate frequency is one of: daily, weekly, biweekly, monthly
   - If frequency is weekly/biweekly, require day_of_week
   - Insert row, commit, return

6. `update_schedule(db, schedule_id: int, data: AIScheduleUpdate) -> AIAnalysisSchedule`
   - Fetch by ID or raise 404
   - Apply non-None fields from update
   - If frequency changed to weekly/biweekly and day_of_week not set, raise 422
   - Commit, return

7. `delete_schedule(db, schedule_id: int) -> None`
   - Fetch by ID or raise 404
   - Delete row, commit

8. `run_scheduled_analysis(db, schedule: AIAnalysisSchedule) -> AIAnalysis | None`
   - Compute `date_from = now - timedelta(days=schedule.time_range_days)`, `date_to = now`
   - Based on `analysis_type`:
     - `communication/conflict/sentiment`: call `run_analysis(db, analysis_type=schedule.general_type or schedule.analysis_type, scope_type=schedule.scope_type, scope_id=schedule.scope_id, date_from, date_to, repo_ids=schedule.repo_ids, triggered_by="scheduled")`
     - `one_on_one_prep`: call `run_one_on_one_prep(db, developer_id=int(schedule.scope_id), date_from, date_to, repo_ids=schedule.repo_ids)`
     - `team_health`: call `run_team_health(db, team=schedule.scope_id if schedule.scope_id != 'all' else None, date_from, date_to, repo_ids=schedule.repo_ids)`
   - Catch `AIFeatureDisabledError` → update `last_run_status='feature_disabled'`
   - Catch `AIBudgetExceededError` → update `last_run_status='budget_exceeded'`
   - Catch general exceptions → update `last_run_status='failed'`, log error
   - On success → update `last_run_at=now`, `last_run_analysis_id=result.id`, `last_run_status='success'`
   - Commit status updates

9. `compute_next_run_description(schedule) -> str`
   - Pure function, no DB needed
   - Returns human-readable string based on frequency/day_of_week/hour/minute
   - Examples: "Daily at 8:00 AM", "Weekly on Monday at 8:00 AM", "Every 2 weeks on Friday at 9:30 AM", "Monthly on the 1st at 6:00 AM"

### backend/app/api/ai_analysis.py

**New schedule endpoints (all admin-only, already on admin router):**

10. `GET /ai/schedules` → `list[AIScheduleResponse]`
    - Calls `list_schedules(db)`
    - Populates `next_run_description` via `compute_next_run_description()`

11. `POST /ai/schedules` → `AIScheduleResponse` (201)
    - Request body: `AIScheduleCreate`
    - Calls `create_schedule(db, data, user.github_username)`
    - After creation: register APScheduler job via `register_schedule_job(app.state.scheduler, schedule)`
    - Return response with `next_run_description`

12. `PATCH /ai/schedules/{schedule_id}` → `AIScheduleResponse`
    - Request body: `AIScheduleUpdate`
    - Calls `update_schedule(db, schedule_id, data)`
    - After update: re-register APScheduler job (remove old, add new if enabled)

13. `DELETE /ai/schedules/{schedule_id}` → 204
    - Calls `delete_schedule(db, schedule_id)`
    - Remove APScheduler job

14. `POST /ai/schedules/{schedule_id}/run` → `AIAnalysisResponse` (201)
    - Manual trigger: calls `run_scheduled_analysis(db, schedule)`
    - Returns the generated analysis or error

### backend/app/main.py

**Scheduler integration:**

15. `register_schedule_job(scheduler, schedule: AIAnalysisSchedule)` helper function:
    - Job ID: `f"ai_schedule_{schedule.id}"`
    - Remove existing job with same ID (ignore if not found)
    - If `schedule.is_enabled`:
      - For `daily`: `scheduler.add_job(..., 'cron', hour=schedule.hour, minute=schedule.minute)`
      - For `weekly`: `scheduler.add_job(..., 'cron', day_of_week=schedule.day_of_week, hour=schedule.hour, minute=schedule.minute)`
      - For `biweekly`: `scheduler.add_job(..., 'interval', weeks=2, ...)` with start_date aligned to next occurrence
      - For `monthly`: `scheduler.add_job(..., 'cron', day=1, hour=schedule.hour, minute=schedule.minute)`
    - Job function: `scheduled_ai_analysis(schedule_id: int)` — loads schedule from DB, calls `run_scheduled_analysis()`

16. On app startup (in lifespan), after existing scheduler setup:
    - Query all enabled schedules: `SELECT * FROM ai_analysis_schedules WHERE is_enabled = true`
    - For each: call `register_schedule_job(scheduler, schedule)`
    - Log count: "Registered N AI analysis schedules"

17. `scheduled_ai_analysis(schedule_id: int)` — async function called by APScheduler:
    - Open DB session
    - Fetch schedule by ID; if not found or disabled, return early
    - Call `run_scheduled_analysis(db, schedule)`
    - Log result with event_type="ai.schedule"

### backend/tests/

18. Test `create_schedule` with valid data → returns schedule with correct fields
19. Test `create_schedule` with weekly frequency but no day_of_week → raises validation error
20. Test `update_schedule` toggle `is_enabled`
21. Test `delete_schedule`
22. Test `run_scheduled_analysis` with `one_on_one_prep` type → calls `run_one_on_one_prep` with correct date range
23. Test `compute_next_run_description` for each frequency type
24. Test API `GET /ai/schedules` returns list with `next_run_description` populated
25. Test API `POST /ai/schedules` returns 201
26. Test API `DELETE /ai/schedules/{id}` returns 204
