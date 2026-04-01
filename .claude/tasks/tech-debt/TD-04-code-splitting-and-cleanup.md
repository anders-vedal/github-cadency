# TD-04: Code Splitting & Dependency Cleanup

## Status: TODO
## Priority: MEDIUM
## Effort: High (multi-day for splitting, low for cleanup)

## Summary

Several backend files have grown past maintainability thresholds. The largest — `stats.py` at 3,394 lines — mixes 8+ metric domains into a single module. Additionally, there are unused dependencies and minor type hint gaps to clean up.

## Tasks

### 1. Split `services/stats.py` (3,394 lines) — HIGH PRIORITY
**Current state:** Contains developer stats, team stats, repo stats, repo summary batch, benchmarks v2, workload, DORA metrics, CI stats, code churn, trends, issue quality, issue linkage, activity summary — all in one file.

**Proposed split:**

| New file | Functions to move | ~Lines |
|----------|-------------------|--------|
| `services/stats_developer.py` | `get_developer_stats()`, `get_all_developers_stats()`, `get_activity_summary()`, `_default_range()`, helper functions | ~600 |
| `services/stats_repo.py` | `get_repo_stats()`, `get_repos_summary()`, `get_code_churn()` | ~400 |
| `services/stats_benchmarks.py` | `get_benchmarks_v2()`, `_compute_per_developer_metrics()`, `BENCHMARK_METRICS`, group config functions | ~500 |
| `services/stats_dora.py` | DORA metric functions, deployment stats | ~400 |
| `services/stats_ci.py` | CI stats functions | ~200 |
| `services/stats_common.py` | Shared helpers: `_default_range()`, `_percentile_band()`, `_linear_regression()`, `_compute_trend()` | ~200 |
| `services/stats.py` | Remaining: team stats, workload, trends, issue quality/linkage. Re-export public API for backward compat. | ~1,100 |

**Approach:**
- Move functions to new files
- Update imports in `api/stats.py` and any other consumers
- Re-export from `stats.py` initially for backward compat, then remove re-exports once all imports updated
- Run tests after each file extraction

### 2. Split `schemas/schemas.py` (1,529 lines) — MEDIUM PRIORITY
**Proposed split by domain:**

| New file | Content |
|----------|---------|
| `schemas/developer.py` | Developer, relationship, activity schemas |
| `schemas/sync.py` | Sync event, schedule, progress schemas |
| `schemas/stats.py` | Stats response, benchmark, workload schemas |
| `schemas/notifications.py` | Notification, config, alert schemas |
| `schemas/ai.py` | AI analysis, settings, usage schemas |
| `schemas/common.py` | Shared enums, base schemas |

### 3. Dependency cleanup — LOW EFFORT
- [ ] Remove `aiohttp` from `backend/requirements.txt` (unused — zero imports)
- [ ] Remove `python-multipart` from `backend/requirements.txt` if no `Form()`/`UploadFile` endpoints exist
- [ ] Add upper bound to apscheduler: `apscheduler>=3.11,<4`
- [ ] Move `shadcn` from `dependencies` to `devDependencies` in `frontend/package.json`
- [ ] Update `aiosqlite` to 0.22.x in `backend/requirements-test.txt`

### 4. Type hint gaps — LOW EFFORT
- [ ] Add `db: AsyncSession` type to 6 handlers in `api/webhooks.py` (lines 77, 84, 110, 140, 163, 171)
- [ ] Add `-> None` or specific return types to webhook handlers

### 5. Health check improvement — LOW EFFORT
**File:** `backend/app/main.py:320`
**Issue:** `GET /api/health` returns `{"status": "ok"}` without checking DB connectivity.
**Fix:** Add a `SELECT 1` probe:
```python
@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(sa.text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return JSONResponse({"status": "degraded", "db": "unreachable"}, status_code=503)
```

### 6. Frontend dependency hygiene — LOW EFFORT
- [ ] Migrate `react-router-dom` imports to `react-router` (20+ files) — v7 compat layer works but v8 may drop it
- [ ] Pin `@base-ui/react` to `~1.3.0` (tilde) until API stabilizes

## Acceptance Criteria

- [ ] `stats.py` split into domain-specific modules, each under 800 lines
- [ ] All existing tests pass after splitting
- [ ] Unused dependencies removed
- [ ] No import changes needed by consumers (re-exports in place initially)

## Notes

- Split `stats.py` first — it's the highest-value refactor
- `schemas.py` split is lower priority since it's mostly type definitions (less cognitive load)
- `github_sync.py` (2,410 lines) is also large but tightly coupled — splitting it is riskier and lower ROI
- Run `/simplify` after each split to catch any missed cleanup
