# Task M-08: Fix N+1 Query Pattern in Benchmarks

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
`_compute_per_developer_metrics()` in `services/stats.py` runs ~9 sequential `db.scalar()` queries per developer in a Python loop. For a 20-person team, this is ~180 sequential queries. This is the most significant performance concern in the stats service, directly impacting the Benchmarks page load time.

### Options
1. **Batch queries** — Rewrite the per-developer metrics as single queries that compute all developers at once (GROUP BY developer). Returns a dict of developer_id → metrics.
2. **Parallel queries** — Use `asyncio.gather()` to run per-developer queries concurrently. Simpler change but still N connections.
3. **Materialized view** — Pre-compute per-developer metrics at sync time. Best performance but adds sync complexity.

Option 1 is the best balance — rewrite the 9 individual queries as 9 team-wide queries with `GROUP BY author_id`/`reviewer_id`, then pivot the results per developer.

### Files
- `backend/app/services/stats.py` — `_compute_per_developer_metrics()`, `get_benchmarks()`

### Architecture Docs
- `docs/architecture/SERVICE-LAYER.md` — Architectural Concerns
