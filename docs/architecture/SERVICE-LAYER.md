---
purpose: "Service responsibilities, cross-service deps, async patterns, sync architecture, key algorithms"
last-updated: "2026-04-22"
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
| `github_sync` | `services/github_sync.py` | ~2400 | GitHub App auth, rate limiting, all upsert helpers, sync orchestration |
| `stats` | `services/stats.py` | ~3200 | All metrics: developer, team, repo, benchmarks v2 (15 metrics), trends, workload, CI, DORA, repos summary, issue linkage by developer |
| `collaboration` | `services/collaboration.py` | ~200 | Collaboration matrix, silos, bus factors, isolation detection |
| `risk` | `services/risk.py` | ~250 | PR risk scoring (pure function + async wrappers) |
| `goals` | `services/goals.py` | ~250 | Goal CRUD, metric computation, auto-achievement |
| `ai_analysis` | `services/ai_analysis.py` | ~1440 | Claude API integration, 1:1 prep briefs, team health checks, Linear sprint/planning context enrichment |
| `ai_settings` | `services/ai_settings.py` | ~300 | AI feature toggles, budget tracking, cooldown, usage summary |
| `work_category` | `services/work_category.py` | ~750 | Work categorization: label/title/AI classification, item drill-down, manual recategorization |
| `relationships` | `services/relationships.py` | ~180 | Developer relationship CRUD + org tree builder |
| `enhanced_collaboration` | `services/enhanced_collaboration.py` | ~400 | Multi-signal collaboration scoring, works-with, over-tagged, communication scores |
| `roles` | `services/roles.py` | ~110 | Role definition CRUD, contribution category lookup, role validation |
| `work_categories` | `services/work_categories.py` | ~550 | Work category + rule CRUD, admin-configurable classification rules, batch reclassify, GitHub data suggestions scan, bulk rule create |
| `teams` | `services/teams.py` | ~100 | Team registry CRUD, `resolve_team()` auto-create, `_validate_team_name()`, rename cascading |
| `slack` | `services/slack.py` | ~350 | Slack config/user settings CRUD, notification senders (DM + channel), scheduled jobs |
| `notifications` | `services/notifications.py` | ~1300 | In-app notification center: alert evaluation (16 types, 10 evaluators), materialization, read/dismiss tracking, config CRUD, auto-resolution |
| `exceptions` | `services/exceptions.py` | ~25 | Custom service-layer exceptions (`AIFeatureDisabledError`, `AIBudgetExceededError`) |
| `ai_schedules` | `services/ai_schedules.py` | ~260 | AI analysis scheduling CRUD, schedule execution, next-run computation |
| `encryption` | `services/encryption.py` | ~35 | Shared Fernet encryption for Slack tokens and Linear API keys |
| `linear_sync` | `services/linear_sync.py` | ~2000 | Linear GraphQL sync orchestration: projects → project updates → cycles → issues (with per-issue comments/history/attachments/relations) → 4-pass PR linker → developer mapping. Rate limit handling covers both HTTP 429 and HTTP 400 `RATELIMITED`. Includes `sanitize_preview()`, `normalize_attachment_source()`, `run_linear_relink()` admin entry point |
| `sprint_stats` | `services/sprint_stats.py` | ~560 | Sprint/planning stats: velocity, completion, scope creep, triage, alignment, estimation accuracy |
| `linear_health` | `services/linear_health.py` | ~360 | Phase 03: 5-signal usage health (adoption, spec quality, autonomy, dialogue health, creator outcome) + `is_linear_primary()` guard |
| `linkage_quality` | `services/linkage_quality.py` | ~170 | Phase 02: PR↔issue linkage summary — confidence/source breakdown + unlinked + disagreement PRs |
| `issue_conversations` | `services/issue_conversations.py` | ~330 | Phase 04: chattiest issues with filters, comment↔bounce scatter, first-response histogram, participant distribution |
| `flow_analytics` | `services/flow_analytics.py` | ~290 | Phase 06: status-time p50/p75/p90/p95, status regressions, triage bounces, refinement churn + readiness gate |
| `bottleneck_intelligence` | `services/bottleneck_intelligence.py` | ~480 | Phase 07: CFD, WIP, review-load Gini, review network, cross-team handoffs, blocked chains, ping-pong, bus factor, bimodal cycle time, top-5 digest |
| `developer_linear` | `services/developer_linear.py` | ~240 | Phase 05: per-developer creator / worker / shepherd profiles from Linear data |
| `github_timeline` | `services/github_timeline.py` | ~480 | Phase 09: `timelineItems` GraphQL fetch (alias-batched), `persist_timeline_events`, `derive_pr_aggregates` (force-push count, ready_for_review, merge queue latency, etc.) |
| `pr_cycle_stages` | `services/pr_cycle_stages.py` | ~180 | Phase 09: per-PR stage decomposition (open→ready→first_review→approved→merged), p50/p75/p90 by stage |
| `codeowners` | `services/codeowners.py` | ~200 | Phase 09: CODEOWNERS parse (comments, wildcards, dir patterns, `**`) + `check_bypass()` detector |
| `ai_cohort` | `services/ai_cohort.py` | ~140 | Phase 10: classify each PR as `human`/`ai_reviewed`/`ai_authored`/`hybrid` via reviewer usernames, labels, commit emails |
| `dora_v2` | `services/dora_v2.py` | ~210 | Phase 10: wraps `get_dora_metrics` with throughput/stability split, rework rate (7-day same-file follow-up), DORA 2024 bands, per-cohort breakdown |
| `incident_classification` | `services/incident_classification.py` | ~120 | Phase 10: hotfix/incident rule engine — default priority-ordered rules (revert, prefix, sev-1/sev-2 labels) |
| `metric_spec` | `services/metric_spec.py` | ~180 | Phase 11: `MetricSpec` registry + `BANNED_METRICS` + `validate_registry()` (raises at import on missing paired outcomes) + `get_catalog()` |
| `utils` | `services/utils.py` | ~15 | Shared utilities (`default_range` date defaulting) |

## Cross-Service Dependencies

```
ai_analysis
  -> ai_settings  (guards: toggle, budget, cooldown, dedup)
  -> stats         (get_developer_stats, get_developer_trends, get_activity_summary, get_benchmarks_v2, get_team_stats, get_workload)
  -> goals         (list_goals, get_goal_progress)
  -> collaboration (get_collaboration)

work_category
  -> ai_settings  (check_feature_enabled, check_budget)

github_sync
  -> work_categories        (classify_work_item_with_rules, get_all_rules -- lazy import)
  -> enhanced_collaboration (post-sync recompute_collaboration_scores -- lazy import, non-blocking)
  -> slack                  (post-sync send_sync_notification -- lazy import, non-blocking)
  -> notifications          (post-sync evaluate_all_alerts -- lazy import, non-blocking)

notifications
  -> risk          (compute_pr_risk for high-risk PR alerts)
  -> ai_settings   (budget check for ai_budget alert)
  -> config        (validate_github_config for missing_config alerts)

slack
  -> stats         (get_team_stats for weekly digest)

stats
  -> roles         (get_role_category_map for contribution-category-aware peer group filtering)

developers (api/developers.py -- inline CRUD)
  -> roles         (validate_role_key)
  -> teams         (resolve_team -- auto-creates teams on developer create/update)

collaboration    (standalone)
enhanced_collaboration (standalone)
relationships    (standalone)
roles            (standalone)
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

- **Read services** (`stats`, `collaboration`, `risk`): No commits. `get_repos_summary()` uses GROUP BY batch queries across all tracked repos (6 queries total for current + previous period) rather than per-repo iteration.
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
    sync_logger: object  # structlog BoundLogger (duck-typed)
    rate_limit_wait_total: int = 0
```

Threaded through the entire sync call chain as the primary state carrier.

### Structured Logging

All services use structlog via `from app.logging import get_logger`:

```python
from app.logging import get_logger
logger = get_logger(__name__)
logger.info("Sync complete", repos=5, event_type="system.sync")
```

Key conventions:
- **Keyword args over format strings**: `logger.info("Found PRs", count=count)` not `logger.info("Found %d PRs", count)`
- **`event_type` on every call**: Enables Loki label filtering (see CLAUDE.md for taxonomy)
- **`str(e)` for exceptions**: `logger.error("Failed", error=str(e))` — structlog serializes the string, not the exception object
- **`LoggingContextMiddleware`** auto-injects `request_id`, `method`, `path` via contextvars — no manual threading needed

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

### Work Categorization

Two layers: **admin-configurable rules** (`work_categories` + `work_category_rules` tables, managed via `services/work_categories.py`) define what categories exist and how items are classified. **Runtime classification** (`services/work_category.py`) applies rules and computes allocation stats.

**Classification cascade** (`classify_work_item_with_rules()` — pure function accepting pre-loaded rules):
1. Label rules: exact match against PR/issue labels (case-insensitive by default)
2. Title regex rules: regex match against title
3. Title prefix rules: prefix match against title
4. Cross-reference: PRs with "unknown" check `closes_issue_numbers` → adopt linked issue's category
5. AI batch classification (optional, via `ai_classify_batch()`)
6. Fallback: "unknown"

Rules evaluated by `priority` (lower = first match wins). All rule definitions stored in `work_category_rules` table, admin-manageable via `GET/POST/PATCH/DELETE /work-categories/rules`. `POST /work-categories/rules/bulk` creates multiple rules in one transaction (used by suggestions approve flow). `POST /work-categories/reclassify` batch-reclassifies all non-manual items using current rules.

**GitHub data suggestions:** `scan_suggestions()` queries distinct labels from `pull_requests.labels` + `issues.labels` (Python-side iteration for SQLite test compat) and distinct `issues.issue_type` values, cross-references against existing rules (case-insensitive for labels), and returns uncovered values with usage counts. Each suggestion includes a `suggested_category` from `_suggest_category()` — a keyword-based hint matcher using `_CATEGORY_HINTS` dict (substring matching against label/type names). No DB changes needed; all data already exists from sync.

Classification provenance tracked via `work_category_source` column: `label`, `title`, `prefix`, `ai`, `manual`, `cross_ref`. Manual overrides (`source="manual"`) are authoritative — never overwritten by sync or reclassify.

**Item drill-down:** `get_work_allocation_items()` fetches all PRs/issues for a date range, classifies each in Python (respecting manual overrides), filters by requested category, and paginates in-memory. Joins Repository and Developer for display names.

**Recategorization:** `recategorize_item()` sets `work_category` and `work_category_source="manual"` on a PR or Issue by ID. Returns the updated item with repo/author info.

### Workload Score

`total_load = open_authored + open_reviewing + open_issues`. Thresholds: low (0), balanced (1-5), high (6-12), overloaded (>12).

### Notification Evaluation (`evaluate_all_alerts`)

Orchestrates 10 evaluators that produce 16 alert types across the system. Each evaluator:
1. Queries current state from the database
2. Upsererts notifications via `_upsert_notification()` (dedup by `alert_key`)
3. Calls `_auto_resolve_stale()` to resolve alerts whose conditions have cleared
4. Returns a set of active `alert_key` values

**Evaluators and their alert types:**

| Evaluator | Alert types | Inputs |
|-----------|------------|--------|
| `_evaluate_stale_pr_alerts` | `stale_pr` (3 sub-checks: no review, unresolved changes, approved-not-merged) | Open PRs vs `stale_pr_threshold_hours` |
| `_evaluate_workload_alerts` | `review_bottleneck`, `underutilized`, `uneven_assignment`, `merged_without_approval` | Review counts, open issues, merged PRs |
| `_evaluate_revert_spike_alert` | `revert_spike` | Merged PR revert rate vs `revert_spike_threshold_pct` |
| `_evaluate_risk_alerts` | `high_risk_pr` | `compute_pr_risk()` on open PRs vs `high_risk_pr_min_level` |
| `_evaluate_collaboration_alerts` | `bus_factor`, `team_silo`, `isolated_developer` | Review distribution, cross-team reviews |
| `_evaluate_trend_alerts` | `declining_trend` | Current vs previous period PR count and review quality |
| `_evaluate_issue_linkage_alerts` | `issue_linkage` | Per-dev linkage rate vs `issue_linkage_threshold_pct` |
| `_evaluate_ai_budget_alert` | `ai_budget` | AI usage vs budget warning threshold |
| `_evaluate_sync_failure_alert` | `sync_failure` | Most recent sync event status |
| `_evaluate_config_alerts` | `unassigned_roles`, `missing_config` | Role assignment + config validation |

**Excluded developers:** `_get_excluded_developer_ids()` queries `role_definitions` by `exclude_contribution_categories` (default: `["system", "non_contributor"]`) and removes matching developers from activity-based evaluators (stale PRs, workload, trends, issue linkage). Collaboration and system alerts are not filtered.

**Error isolation:** Each evaluator is wrapped in try/except — a failure in one does not prevent others from running.

### Collaboration Insights (`_compute_insights`)

- **Silos**: Cross-team pairs with no reviews between them
- **Bus factors**: Reviewers with >70% of reviews per repo
- **Isolated developers**: 0 reviews given AND <=1 unique reviewer

## Architectural Concerns

| Severity | Area | Description |
|----------|------|-------------|
| ~~High~~ | ~~AI~~ | ~~`ai_analysis.py` imports `get_benchmarks` (renamed to `get_benchmarks_v2`)~~ — **Fixed**: Updated imports |
| ~~High~~ | ~~Boundaries~~ | ~~`ai_settings.check_feature_enabled` and `ai_analysis.run_*` raise `HTTPException` from service layer~~ — **Resolved:** Services now raise `AIFeatureDisabledError`/`AIBudgetExceededError` from `services/exceptions.py`; API routes catch and convert |
| ~~Medium~~ | ~~Performance~~ | ~~`_compute_per_developer_metrics()` fires ~9 queries per developer~~ — **Resolved:** Rewritten as 4 batch GROUP BY queries |
| ~~Medium~~ | ~~Sync~~ | ~~TOCTOU race on sync start without DB-level locking~~ — **Resolved:** PostgreSQL advisory lock wraps check+insert |
| Medium | Sync | `scheduled_sync()` calls `await run_sync(...)` directly — long-running syncs block other APScheduler jobs (Slack scheduled checks) |
| Medium | Sync | `github_get()` for check-runs (`/commits/{sha}/check-runs`) only processes the first page — silently truncates CI data for PRs with many checks |
| Medium | Side effect | `get_goal_progress()` auto-achieves goals during what appears to be a read operation |
| Medium | AI | `_call_claude_and_store()` (internal helper) does NOT apply feature/budget guards — any code calling it directly bypasses budget checks |
| Medium | Notifications | `evaluate_all_alerts()` dispatches all evaluators but routes some differently (ai_budget and sync_failure skip `excluded_dev_ids`, config evaluator also skips it) — the conditional dispatch in the for-loop is fragile; a table-driven approach would be cleaner |
| Medium | Notifications | `_evaluate_stale_pr_alerts` has 3 independent sub-queries (no-review, changes-requested, approved-not-merged) that could produce overlapping `alert_key`s for the same PR — dedup via `active_keys` set prevents DB duplicates but the "approved but not merged" check redundantly re-queries PRs already covered |
| Low | DRY | `_default_range()` duplicated in 5 service files (stats, collaboration, risk, work_category, enhanced_collaboration) |
| Low | AI data | Correlated subquery in `_gather_developer_texts()` for issue comment filtering |
