---
purpose: "Service responsibilities, cross-service deps, async patterns, sync architecture, key algorithms"
last-updated: "2026-03-29"
related:
  - docs/architecture/OVERVIEW.md
  - docs/architecture/API-DESIGN.md
  - docs/architecture/DATA-MODEL.md
  - docs/architecture/DATA-FLOWS.md
---

# Service Layer

## Service Responsibility Map

| Service | File | LOC | Role |
|---------|------|-----|------|
| `github_sync` | `services/github_sync.py` | ~1860 | GitHub App auth, rate limiting, all upsert helpers, sync orchestration |
| `stats` | `services/stats.py` | ~2500 | All metrics: developer, team, repo, benchmarks, trends, workload, CI, DORA |
| `collaboration` | `services/collaboration.py` | ~200 | Collaboration matrix, silos, bus factors, isolation detection |
| `risk` | `services/risk.py` | ~250 | PR risk scoring (pure function + async wrappers) |
| `goals` | `services/goals.py` | ~250 | Goal CRUD, metric computation, auto-achievement |
| `ai_analysis` | `services/ai_analysis.py` | ~800 | Claude API integration, 1:1 prep briefs, team health checks |
| `ai_settings` | `services/ai_settings.py` | ~300 | AI feature toggles, budget tracking, cooldown, usage summary |
| `work_category` | `services/work_category.py` | ~350 | Work categorization: label/title/AI classification |
| `relationships` | `services/relationships.py` | ~180 | Developer relationship CRUD + org tree builder |
| `enhanced_collaboration` | `services/enhanced_collaboration.py` | ~400 | Multi-signal collaboration scoring, works-with, over-tagged, communication scores |
| `slack` | `services/slack.py` | ~350 | Slack config/user settings CRUD, notification senders (DM + channel), scheduled jobs |
| `exceptions` | `services/exceptions.py` | ~25 | Custom service-layer exceptions (`AIFeatureDisabledError`, `AIBudgetExceededError`) |
| `utils` | `services/utils.py` | ~15 | Shared utilities (`default_range` date defaulting) |

## Cross-Service Dependencies

```
ai_analysis
  -> ai_settings  (guards: toggle, budget, cooldown, dedup)
  -> stats         (get_developer_stats, get_developer_trends, get_benchmarks, get_team_stats, get_workload)
  -> goals         (list_goals, get_goal_progress)
  -> collaboration (get_collaboration)

work_category
  -> ai_settings  (check_feature_enabled, check_budget)

github_sync
  -> enhanced_collaboration (post-sync recompute_collaboration_scores -- lazy import, non-blocking)
  -> slack                  (post-sync send_sync_notification -- lazy import, non-blocking)

slack
  -> stats         (get_team_stats for weekly digest)

stats            (standalone)
collaboration    (standalone)
enhanced_collaboration (standalone)
relationships    (standalone)
risk             (standalone)
goals            (standalone)
ai_settings
  -> exceptions  (raises AIFeatureDisabledError)
slack            (standalone except for stats dependency in weekly digest)
```

All cross-service imports are **deferred** (inside function bodies) to avoid circular import at module load time.

## Async Patterns

### Session Management

**Pattern 1: FastAPI DI** -- used by all API-triggered service calls. `Depends(get_db)` yields an `AsyncSession` with `expire_on_commit=False`. Service functions accept `db: AsyncSession` as first param.

**Pattern 2: Self-owned session** -- used by `run_sync()`, `run_contributor_sync()`, and `webhooks.py`. These create their own `AsyncSessionLocal()` context because they run outside the request lifecycle (background tasks, scheduler, webhooks).

### Commit Patterns

- **Read services** (`stats`, `collaboration`, `risk`): No commits
- **Write services** (`goals`, `ai_analysis`, `ai_settings`): Commit after mutations
- **Sync service**: Per-repo commits + batch commits every 50 PRs + progress commits every 10 items

## GitHub API Integration

### Authentication

GitHub App auth via JWT: `github_sync.py` builds a JWT from the App's private key, exchanges it for an installation token via `POST /app/installations/{id}/access_tokens`. Token cached for 1 hour.

### Rate Limiting

- `check_rate_limit()`: Reads `X-RateLimit-Remaining` headers after each request; sleeps until reset if exhausted
- `proactive_rate_check()`: Pre-checks remaining quota before starting a repo; sleeps if below threshold
- `github_get()`: Single GET with retry on 502/503/504 with exponential backoff
- `github_get_paginated()`: Follows `Link: rel="next"` headers for paginated responses

### Upsert Pattern

All upsert helpers (`upsert_pull_request`, `upsert_review`, etc.) follow:
1. SELECT by unique key (e.g., `repo_id + number` for PRs)
2. CREATE if not found
3. Always overwrite mutable fields
4. `db.flush()` (not commit -- batch commits happen at a higher level)

## Sync Architecture

### SyncContext

```python
@dataclass
class SyncContext:
    db: AsyncSession
    client: httpx.AsyncClient
    sync_event: SyncEvent
    sync_logger: logging.Logger
    rate_limit_wait_total: int = 0
```

Threaded through the entire sync call chain as the primary state carrier.

### Per-Repo Processing Steps

Each repo goes through these sequential steps (tracked via `current_step`):

1. **fetching_prs**: Paginated fetch of all/updated PRs
2. **processing_prs**: For each PR: upsert PR, fetch+upsert reviews, comments, files, check runs. Batch commit every 50 PRs.
3. **fetching_issues / processing_issues**: Fetch and upsert issues (excluding PRs). Commit every 10.
4. **processing_issue_comments**: Fetch and upsert all issue comments
5. **syncing_file_tree**: DELETE all + INSERT fresh from Git Trees API
6. **fetching_deployments**: GitHub Actions workflow runs (only if `DEPLOY_WORKFLOW_NAME` set). Fetches all completed runs (success + failure), computes lead times for successful deploys, then runs `detect_deployment_failures()` to flag failures (3 signals: failed workflow, revert PRs within 48h, hotfix PRs within 48h) and link recovery deployments for MTTR.

### Error Isolation

Per-repo failure is isolated via rollback + merge pattern:
1. Preserve `log_summary` in local variable
2. `await db.rollback()`
3. `await db.merge(sync_event)` -- re-attach detached object
4. Restore log_summary, append to `repos_failed` and `errors`
5. Commit and continue to next repo

### Concurrency Control

`run_sync()` uses a PostgreSQL advisory lock (`pg_advisory_lock`) to prevent TOCTOU race between the "is another sync running?" check and the SyncEvent INSERT. Lock is acquired before the check and released after the INSERT commits. SQLite (tests) gracefully skips the advisory lock.

### Cancellation

`_check_cancel()` re-queries the DB for `cancel_requested` at repo boundaries and every 50-PR batch. On `True`, raises `SyncCancelled` -> status becomes `"cancelled"` + `is_resumable=True`.

### Contributor Sync

`sync_org_contributors()` fetches `GET /orgs/{org}/members` and upserts developers. Runs at the start of every `run_sync()` and standalone via `POST /sync/contributors`. If a previously deactivated developer is found in the org member list, they are auto-reactivated with a warning log entry visible in the sync detail page.

### Backfill

`backfill_author_links()` bulk-updates NULL `author_id`/`reviewer_id`/`assignee_id` FKs using stored `_github_username` columns with EXISTS guard. Called after every sync. Post-backfill, `recompute_collaboration_scores()` runs with `since_override` or a 90-day window for full syncs (not the default 30 days).

### Active Developer Filtering

All team-scoped queries in `stats.py`, `risk.py`, `collaboration.py`, and `work_category.py` filter on `Developer.is_active.is_(True)` before computing metrics. Inactive developers are excluded from:
- Team stats, benchmarks, workload, and trend comparisons
- Repo top contributors list
- Risk summary team filtering
- Collaboration matrix and insights
- Work allocation stats
- Issue quality and creator stats (team filter path)

Individual developer stats (`get_developer_stats`, `get_developer_trends`) and goals are **not** filtered — you can still fetch stats for an inactive developer by ID to view their historical data.

## AI Integration

### Guard Chain (every AI call)

1. `check_feature_enabled(db, feature_name)` -- checks master switch + per-feature toggle. Raises `AIFeatureDisabledError`.
2. `check_budget(db, ai_settings)` -- sums current month tokens. Raises `AIBudgetExceededError` if over budget.
3. `find_recent_analysis(db, ...)` -- dedup within cooldown window. Returns cached result if found.

API routes catch `AIFeatureDisabledError` → 403 and `AIBudgetExceededError` → 429. Custom exceptions from `services/exceptions.py` keep services decoupled from FastAPI's HTTP layer.

### Dedup Mechanism

Reused analyses store `reused_from_id` pointing to the original. Budget excludes reused rows. `find_recent_analysis()` only matches non-reused rows to prevent chaining.

### Claude API Call

`anthropic.AsyncAnthropic`, model `claude-sonnet-4-0`, `max_tokens=4096`, `max_retries=3`, `timeout=120s`. Response parsed as JSON; on parse failure stored as `{"raw_text": ..., "parse_error": True}`.

## Key Algorithms

### Review Quality Classification (`classify_review_quality`)

Pure function. Tiers based on review state, body length, and comment analysis:
- **thorough**: CHANGES_REQUESTED with substantive body, or APPROVED with >=2 substantive comments
- **standard**: Body length >50, or has comments
- **rubber_stamp**: APPROVED with no body and no comments
- **minimal**: Everything else

Score formula: `(rubber_stamp*0 + minimal*1 + standard*3 + thorough*5) / total * 2` (scale 0-10)

### PR Risk Scoring (`compute_pr_risk`)

Pure function, 10 weighted factors summed (capped at 1.0):

| Factor | Weight | Condition |
|--------|--------|-----------|
| `very_large_pr` | 0.35 | additions > 1000 |
| `large_pr` | 0.20 | additions > 500 |
| `many_files` | 0.10 | changed_files > 15 |
| `new_contributor` | 0.15 | merged < 5 or not in registry |
| `no_review` | 0.25 | merged with 0 approvals |
| `rubber_stamp_only` | 0.20 | all reviews are rubber_stamp |
| `fast_tracked` | 0.15 | merged in < 2h |
| `self_merged` | 0.10 | author == merger |
| `high_review_rounds` | 0.10 | review_round_count >= 3 |
| `hotfix_branch` | 0.10 | branch starts with hotfix/ or fix/ |

Levels: low (<0.3), medium (0.3-0.6), high (0.6-0.8), critical (>=0.8).

### Percentile Bands (`_percentile_band`)

Uses `statistics.quantiles(n=4)`. For lower-is-better metrics (in `_LOWER_IS_BETTER` set), labels are inverted so `above_p75` always means "best performance."

### Trend Regression (`_linear_regression`)

Simple OLS over N period buckets. Direction is polarity-aware: for lower-is-better metrics, a negative slope = "improving". Change < 5% = "stable".

### Work Categorization (`classify_work_item`)

Three tiers: (1) label map (exact lowercase), (2) title regex patterns, (3) "unknown". Optional AI batch classification for unknowns via `ai_classify_batch()`.

### Workload Score

`total_load = open_authored + open_reviewing + open_issues`. Thresholds: low (0), balanced (1-5), high (6-12), overloaded (>12).

### Collaboration Insights (`_compute_insights`)

- **Silos**: Cross-team pairs with no reviews between them
- **Bus factors**: Reviewers with >70% of reviews per repo
- **Isolated developers**: 0 reviews given AND <=1 unique reviewer

## Architectural Concerns

| Severity | Area | Description |
|----------|------|-------------|
| ~~High~~ | ~~Boundaries~~ | ~~`ai_settings.check_feature_enabled` and `ai_analysis.run_*` raise `HTTPException` from service layer~~ — **Resolved:** Services now raise `AIFeatureDisabledError`/`AIBudgetExceededError` from `services/exceptions.py`; API routes catch and convert |
| ~~Medium~~ | ~~Performance~~ | ~~`_compute_per_developer_metrics()` fires ~9 queries per developer~~ — **Resolved:** Rewritten as 4 batch GROUP BY queries |
| ~~Medium~~ | ~~Sync~~ | ~~TOCTOU race on sync start without DB-level locking~~ — **Resolved:** PostgreSQL advisory lock wraps check+insert |
| Medium | Side effect | `get_goal_progress()` auto-achieves goals during what appears to be a read operation |
| Low | DRY | `_default_range()` duplicated in 5 service files (stats, collaboration, risk, work_category, enhanced_collaboration) |
| Low | AI data | Correlated subquery in `_gather_developer_texts()` for issue comment filtering |
