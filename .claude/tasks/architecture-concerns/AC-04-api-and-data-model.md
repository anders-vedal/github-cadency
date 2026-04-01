# AC-04: API & Data Model Concerns

**Priority:** Backlog
**Severity:** Low-Medium
**Effort:** Low
**Status:** Pending

## Finding #1: Inline Business Logic in Routers

- **Files:**
  - `backend/app/api/ai_analysis.py` — `POST /ai/estimate` has ~75 lines of inline logic
  - `backend/app/api/sync.py` — `GET /sync/status` runs 5 inline SQL queries via `_build_sync_status()`
  - `backend/app/api/developers.py` — `GET /deactivation-impact` runs 3 aggregate queries inline
- These violate the thin-router delegation pattern documented in API-DESIGN.md
- Not a bug, but increases coupling and makes testing harder

### Required Changes
1. Extract `POST /ai/estimate` logic into `services/ai_analysis.py:estimate_cost()`
2. Extract `_build_sync_status()` into `services/github_sync.py:get_sync_status()`
3. Extract deactivation impact queries into `services/stats.py` or a dedicated service function
4. Low priority — these are read-only operations with no domain logic complexity

## Finding #2: Circular Import in sync.py

- **File:** `backend/app/api/sync.py:313`
- `PATCH /sync/schedule` does `from app.main import reschedule_sync_jobs` inside the function body
- `main.py` imports `sync` router → circular dependency at module level
- The deferred import works but is fragile and non-obvious

### Required Changes
1. Option A: Move `reschedule_sync_jobs()` to a shared module (e.g., `services/scheduler.py`)
2. Option B: Pass the scheduler reference via `request.app.state.scheduler` and have the route call scheduler methods directly
3. Option C: Accept the deferred import — it's a common Python pattern and unlikely to break

## Finding #3: CLAUDE.md Table Count Stale

- **File:** `CLAUDE.md:111`
- Header says "Database Schema (29 tables)" but actual count is 32 (5 notification tables from migration 033)
- Architecture docs (DATA-MODEL.md, OVERVIEW.md) now correctly say 32

### Required Changes
1. Update `CLAUDE.md` line 111: change "29 tables" to "32 tables"
2. Add the 5 notification tables to the table listing in CLAUDE.md

## Finding #4: Service-Only FK Enforcement

- **Files:** `backend/app/models/models.py`
- `developers.role` references `role_definitions.role_key` — validated at API layer only, no DB FK constraint
- `developers.team` has a DB FK to `teams.name` (added in migration 031) — inconsistent with the role approach
- `ai_analyses.reused_from_id` is a plain Integer, not a FK — no referential integrity

### Required Changes
1. These are deliberate design decisions documented in DATA-MODEL.md
2. Adding DB FKs for `role` would require migration + handling of existing NULL/invalid values
3. `reused_from_id` intentionally avoids cascade complications
4. No change needed — document as accepted trade-offs

## Finding #5: Silent No-Op on Undismiss Endpoints

- **File:** `backend/app/services/notifications.py:1272-1295`
- `DELETE /notifications/dismissals/{id}` and `DELETE /notifications/type-dismissals/{id}` return `{"success": true}` even when the dismissal_id doesn't exist
- The service checks `if row:` and only deletes if found, but always returns success
- No 404 is raised for missing records

### Required Changes
1. Option A: Raise `HTTPException(404)` when the dismissal is not found
2. Option B: Return `{"success": false, "reason": "not_found"}` for missing records
3. Recommendation: Option A is more RESTful and matches patterns in other routers

## Finding #6: _default_range() Duplicated Across 5 Services

- **Files:** `backend/app/services/stats.py`, `collaboration.py`, `risk.py`, `work_category.py`, `enhanced_collaboration.py`
- Each file has its own copy of the date range defaulting logic
- Already extracted to `services/utils.py:default_range` but old copies may remain

### Required Changes
1. Verify all 5 service files import from `services/utils.py` (some may already)
2. Remove any remaining inline `_default_range()` definitions
3. Low priority — functional correctness is not affected
