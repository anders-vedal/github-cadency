---
purpose: "Step-by-step data flows with file:function references for all major operations"
last-updated: "2026-04-01"
related:
  - docs/architecture/OVERVIEW.md
  - docs/architecture/SERVICE-LAYER.md
  - docs/architecture/API-DESIGN.md
---

# Data Flows

## 1. GitHub Sync Pipeline

### Trigger

Three entry points converge on `run_sync()`:

1. **Scheduled incremental**: `main.py:scheduled_sync()` fires every `incremental_interval_minutes` (loaded from `sync_schedule_config` DB table, default 15) via APScheduler. Checks `auto_sync_enabled` at runtime before proceeding.
2. **Scheduled full**: same wrapper, cron-based at `full_sync_cron_hour` (default 2 AM)
3. **API-triggered**: `api/sync.py:start_sync()` -> `BackgroundTasks.add_task(run_sync, ...)`
4. **Startup resume**: `main.py:_recover_orphaned_syncs()` — finds any `SyncEvent` with `status='started'`, force-cancels it, then fires `asyncio.create_task(run_sync(...))` for the most recent one

Resume: `api/sync.py:resume_sync()` computes remaining repo IDs from `repos_completed` and passes them to `run_sync()`.

### Orchestration (`services/github_sync.py:run_sync`)

```
1. Concurrency guard: PostgreSQL advisory lock (key 1937337955) + SELECT SyncEvent WHERE status="started"
2. Create SyncEvent(status="started"), commit, release advisory lock
3. Open httpx.AsyncClient (GitHub App JWT -> installation token)
4. If not resume: fetch org repos via github_get_paginated, upsert repos
5. sync_org_contributors(db, client, ctx) -> upsert Developer rows
   - If existing developer has is_active=False: set is_active=True, flush, emit warning log
6. For each tracked repo:
   a. _check_cancel() -> SyncCancelled if cancel_requested
   b. _clear_repo_progress() -> reset progress fields
   c. proactive_rate_check()
   d. sync_repo(ctx, repo, since=...)
7. backfill_author_links(db) -> bulk UPDATE null FKs
8. recompute_collaboration_scores(db, since, now) -> materialized pair scores (non-blocking on failure)
9. send_sync_notification(db, sync_event) -> Slack notification (non-blocking on failure)
10. Set status: completed | completed_with_errors | failed | cancelled
10. finally: clear progress, set completed_at/duration_s, commit
```

### Per-Repo Sync (`services/github_sync.py:sync_repo`)

```
0. Load classification rules once: work_categories.get_all_rules(db)
1. [fetching_prs] github_get_paginated(/repos/{name}/pulls)
2. [processing_prs] For each PR:
   a. upsert_pull_request() -> SELECT by (repo_id, number), create/update
      - resolve_author(): if matching developer is inactive, auto-reactivates (is_active=True, flush, warning log)
      - classify_work_item_with_rules(pr.labels, pr.title, rules) -> set work_category + work_category_source (skip if source="manual")
   b. github_get_paginated(/pulls/{n}/reviews) -> upsert_review() each
   c. github_get_paginated(/pulls/{n}/comments) -> upsert_review_comment() each
      - classify_comment_type() for each comment
   d. db.flush() -> recompute_review_quality_tiers(db, pr)
   e. compute_approval_metrics(db, pr)
   f. Count CHANGES_REQUESTED -> review_round_count
   g. github_get_paginated(/pulls/{n}/files) -> upsert_pr_file() each
   h. In upsert_review_comment(): extract_mentions(body) -> comment.mentions JSONB
   i. github_get(/commits/{head_sha}/check-runs) -> upsert_check_run() each
   i. Every 50 PRs: batch commit + _check_cancel()
   j. Every 10 PRs: progress commit
3. [fetching_issues] github_get_paginated(/repos/{name}/issues)
4. [processing_issues] For each (non-PR) issue:
   a. upsert_issue() -> time_to_close_s, quality fields
      - classify_work_item_with_rules(issue.labels, issue.title, rules) -> set work_category + work_category_source (skip if source="manual")
   b. Every 10 issues: progress commit
5. [processing_issue_comments] github_get_paginated(/issues/comments)
   a. Match to parent issue via issue_url
   b. upsert_issue_comment() -> extract_mentions(body) -> comment.mentions JSONB
6. [syncing_file_tree] DELETE all RepoTreeFile for repo, INSERT from /git/trees/{branch}?recursive=1
7. [fetching_deployments] If DEPLOY_WORKFLOW_NAME set:
   a. Fetch Actions workflow runs (manual pagination — response structure differs from standard)
   b. upsert_deployment() each
   c. compute_deployment_lead_times()
   d. detect_deployment_failures() -> flag failures (3 signals: failed workflow, revert PRs within 48h, hotfix PRs), link recovery deployments for MTTR
8. Commit, update repo.last_synced_at
```

### Post-Sync Hooks

After sync completes (step 10 of orchestration):

```
10a. evaluate_all_alerts(db) -> notification evaluation (lazy import, non-blocking)
10b. send_sync_notification(db, sync_event) -> Slack notification (lazy import, non-blocking)
```

### Error Isolation (per-repo failure)

```
1. Save sync_event.log_summary to local variable
2. await db.rollback()
3. await db.merge(sync_event) -> re-attach to session
4. Restore log_summary, append to repos_failed/errors
5. Commit, continue to next repo
```

### Backfill (`services/github_sync.py:backfill_author_links`)

```
UPDATE pull_requests SET author_id = (SELECT id FROM developers WHERE ...)
  WHERE author_id IS NULL AND author_github_username IS NOT NULL
  AND EXISTS (SELECT 1 FROM developers WHERE ...)
-- Same for pr_reviews.reviewer_id, issues.assignee_id, and issues.creator_id
```

## 2. Webhook Processing

**Entry**: `api/webhooks.py:github_webhook`

```
1. verify_signature() -> hmac.compare_digest(X-Hub-Signature-256)
2. Open AsyncSessionLocal() + httpx.AsyncClient (own lifecycle)
3. Route by X-GitHub-Event header:
   - pull_request:
     a. Get/create repo
     b. upsert_pull_request()
     c. Re-fetch ALL reviews + comments for this PR
     d. recompute_review_quality_tiers()
   - pull_request_review:
     a. Lookup PR (upsert if missing)
     b. upsert_review()
     c. Re-fetch all review comments
     d. recompute_review_quality_tiers()
   - pull_request_review_comment:
     a. Lookup PR (skip if missing -- silent drop)
     b. upsert_review_comment()
   - issues:
     a. Get/create repo
     b. upsert_issue()
   - issue_comment:
     a. Skip if PR-linked
     b. Get/create issue
     c. upsert_issue_comment()
4. Single commit for all handlers
5. On exception: rollback, re-raise as 500
```

## 3. Stats Computation

**Entry**: `services/stats.py:get_developer_stats` (and similar)

```
1. _default_range(date_from, date_to) -> default to last 30 days
2. ~20 independent scalar queries (each awaited sequentially):
   - Merged PR count, opened PR count
   - Avg/median time_to_merge_s, time_to_first_review_s
   - Review counts by tier, review quality score
   - Open PR/issue counts (drafts excluded)
   - Issue stats, approval metrics
3. Assemble into DeveloperStatsResponse
```

### Benchmarks v2 (`services/stats.py:get_benchmarks_v2`)

```
1. Load group config from benchmark_group_config (roles + metrics for this group)
2. Resolve developers matching group roles (via role_definitions contribution categories)
3. _compute_per_developer_metrics(db, dev_ids, date_from, date_to, requested_metrics):
   - Batch GROUP BY queries (only for requested metrics), NOT per-developer N+1
4. _percentile_band() per metric per developer (inverts for lower-is-better)
5. Optional team comparison: per-team medians when >=2 teams meet min_team_size
6. Assemble BenchmarksV2Response
```

### Trends (`services/stats.py:get_developer_trends`)

```
1. Build N period buckets (weekly/monthly/sprint), iterating backwards
2. For each bucket: ~5 scalar queries
3. _linear_regression(x, y) -> slope, intercept
4. _trend_direction(slope, values, metric) -> improving/worsening/stable
   - Polarity-aware: for lower-is-better, negative slope = improving
   - |change_pct| < 5% = stable
```

## 4. AI Analysis Lifecycle

**Entry**: `services/ai_analysis.py:run_analysis`

```
1. GUARD: check_feature_enabled(db, feature) -> 403 if disabled
2. GUARD: check_budget(db, settings) -> 429 if over budget
3. DEDUP: find_recent_analysis(db, type, scope, cooldown)
   - If found and force=False: create reuse pointer row, return
4. GATHER: _gather_scope_texts(db, scope_type, scope_id, date_from, date_to)
   - Routes to _gather_developer_texts or _gather_team_texts
   - Collects PR descriptions, review bodies, issue comments (truncated to 500 chars, max 50 items per category)
5. CALL: _call_claude_and_store()
   a. Build prompt with analysis_type-specific instructions
   b. anthropic.AsyncAnthropic.messages.create(model="claude-sonnet-4-0", max_tokens=4096)
   c. Strip markdown fences from response
   d. json.loads() response -> result JSONB
   e. On parse failure: store {"raw_text": ..., "parse_error": True}
   f. Create AIAnalysis row with split token tracking + cost
6. Commit and return
```

### 1:1 Prep (`services/ai_analysis.py:run_one_on_one_prep`)

```
1. Same guard chain
2. Gather enriched context:
   - get_developer_stats() + get_developer_trends() + get_benchmarks_v2()
   - Fetch recent PRs with review details
   - list_goals() + get_goal_progress() for each
   - get_issue_creator_stats()
   - gather_sprint_context_for_developer() — active sprint, recent sprints,
     triage stats, estimation patterns (only when Linear active + dev mapped)
3. Build structured prompt with all metrics
4. _call_claude_and_store()
```

### Team Health (`services/ai_analysis.py:run_team_health`)

```
1. Same guard chain
2. Gather team context:
   - get_team_stats() + get_workload() + get_collaboration()
   - Per-developer stats for all team members
   - gather_planning_health_context() — velocity trend, completion rate, scope creep,
     triage health, estimation accuracy, work alignment, at-risk projects
     (only when Linear active; reuses sprint_stats.py functions)
3. _call_claude_and_store()
```

## 5. Auth Flow

```
1. Frontend: window.location = GET /api/auth/login -> returns GitHub OAuth URL
2. Browser -> GitHub OAuth authorize page
3. GitHub -> redirect to frontend /auth/callback?code=...
4. Frontend: AuthCallback component calls GET /api/auth/callback?code=...
5. Backend (api/oauth.py:callback):
   a. POST https://github.com/login/oauth/access_token (exchange code)
   b. GET https://api.github.com/user (fetch profile)
   c. SELECT Developer by github_username
   d. If not found: CREATE Developer(app_role="developer")
      - If username matches devpulse_initial_admin AND no admin exists: app_role="admin"
   e. If is_active=False: return 403
   f. create_jwt(dev.id, username, app_role, token_version) -> HS256, 4-hour expiry
   g. Return 302 redirect to frontend /auth/callback#token={jwt}
6. Frontend AuthCallback: store token in localStorage, redirect to /

Per-request auth:
1. apiFetch() adds Authorization: Bearer <token> header
2. Backend: get_current_user() decodes JWT, queries developers.is_active + token_version
   - 401 if token invalid/expired, developer not found, is_active=False, or token_version mismatch
3. require_admin() checks app_role == "admin"
4. On 401: frontend clears token, redirects to /login
```

## 6. Goal Lifecycle

```
CREATE (api/goals.py -> services/goals.py:create_goal):
1. Validate developer exists
2. _get_metric_value(db, dev_id, metric_key, 30-day window) -> baseline
3. INSERT DeveloperGoal with baseline_value and created_by

PROGRESS (api/goals.py -> services/goals.py:get_goal_progress):
1. Load goal
2. Build 8 weekly history points: _get_metric_value() for each week
3. AUTO-ACHIEVEMENT: if active and metric crossed target for last 2 periods:
   - SET status="achieved", achieved_at=now (side effect on GET)
4. Return GoalProgressResponse with history + current value

UPDATE:
- Admin: update_goal() -> can change status, notes
- Self: update_goal_self() -> can change target_value, target_date, status, notes
  - Guard: created_by must be "self"
```

## 7. Collaboration Analysis

**Entry**: `services/collaboration.py:get_collaboration`

```
1. _default_range()
2. Single GROUP BY query: reviewer_id, author_id with state breakdown
3. Build pair_data dict with review_count, approved, changes_requested
4. _compute_insights(pair_data, developer_map):
   - Silos: cross-team pairs with no reviews (O(T^2) where T = team count)
   - Bus factors: reviewers with >70% of reviews per repo
   - Isolated: 0 reviews given AND <=1 unique reviewer received
   - Strongest pairs: top 10 by mutual review count
5. Return CollaborationResponse
```

## 7b. Enhanced Collaboration (Multi-Signal)

**Entry**: `services/enhanced_collaboration.py`

### Collaboration Score Recomputation (post-sync)

```
recompute_collaboration_scores(db, date_from, date_to):
1. Query 5 signals in parallel:
   a. PR reviews: (reviewer_id, author_id) from pr_reviews JOIN pull_requests
   b. Co-repo authoring: distinct (repo_id, author_id) from merged PRs -> pair combos
   c. Issue co-comments: (issue_id, author_username) from issue_comments -> pair combos
   d. @mentions: mentions JSONB from pr_review_comments + issue_comments -> author->mentioned pairs
   e. Co-assignment: (assignee_id, creator_username) from issues -> pair combos
2. For each unique pair (canonical a_id < b_id):
   a. Normalize each signal: min(count / cap, 1.0)
   b. Weighted sum: reviews*0.35 + issue_comments*0.20 + coauthor*0.15 + mentions*0.15 + co_assigned*0.15
3. DELETE old scores for this period, bulk INSERT new DeveloperCollaborationScore rows
4. Commit
```

### Works-With Query

```
get_works_with(db, developer_id, date_from, date_to, limit):
1. SELECT from developer_collaboration_scores WHERE a_id = dev OR b_id = dev
2. ORDER BY total_score DESC, LIMIT N
3. JOIN developers for display info
4. Return WorksWithResponse
```

### Over-Tagged Detection

```
get_over_tagged(db, team, date_from, date_to):
1. Count PRs touched (authored + reviewed) per developer
2. Count issues touched (assigned) per developer
3. combined_rate = (prs + issues) / (total_prs + total_issues)
4. Flag if rate > avg + 1.5*stddev OR rate > 0.5
5. Severity: mild (1.5-2σ), moderate (2-3σ or >50%), severe (>3σ or >70%)
```

### Communication Score

```
get_communication_scores(db, team, date_from, date_to):
Per developer, 4 components (25 pts each, total 0-100):
1. review_engagement = min(reviews_given / team_median, 1.0) * 25
2. comment_depth = min(avg_comment_length / 200, 1.0) * 25
3. reach = min(unique_devs_interacted / (team_size - 1), 1.0) * 25
4. responsiveness = (1 - min(avg_review_time_h / 24, 1.0)) * 25
```

## 8. Work Categorization

**Entry**: `services/work_category.py:get_work_allocation`

```
1. Fetch merged PRs + created issues for period
2. Load classification rules from DB: work_categories.get_all_rules(db)
3. For each item, classify_work_item_with_rules(labels, title, rules):
   a. Label rules: exact match against PR/issue labels (by priority)
   b. Title regex rules: regex match against title (by priority)
   c. Title prefix rules: prefix match against title (by priority)
   d. Fallback: "unknown"
   e. For items with stored work_category (non-manual): use stored value if deterministic = "unknown"
   f. Manual overrides (work_category_source="manual"): never overwritten
4. cross_reference_pr_categories(prs, issues):
   - PRs with "unknown": check closes_issue_numbers -> adopt linked issue's category
5. If use_ai=True:
   a. Collect remaining unknowns
   b. ai_classify_batch(items, db):
      - check_feature_enabled + check_budget
      - Batch up to 200 items -> Claude API
      - Validate response indices and categories (against valid category_keys from DB)
      - Return {item_id: category}
   c. Apply AI results, write work_category back to DB
6. Aggregate into CategoryAllocation + per-developer + trend buckets
```

### Admin-Configurable Rules

Categories and rules are managed via the `/api/work-categories` API surface (`services/work_categories.py`):
- Categories: CRUD with `exclude_from_stats` toggle, color, display_order
- Rules: CRUD with `match_type` (label/title_regex/prefix), `match_value`, `priority`, `case_sensitive`
- Reclassify: `POST /work-categories/reclassify` re-runs all rules against non-manual items
- At sync time: `github_sync.py` lazy-imports `classify_work_item_with_rules` and `get_all_rules` to classify PRs and issues

## 9. App Startup

**Entry**: `main.py:lifespan()`

```
1. _log_config_warnings() — validate GitHub App config
2. _recover_orphaned_syncs() — detect and resume any sync stuck in "started" status
3. Load SyncScheduleConfig from DB (singleton id=1); fallback to env var defaults
4. Create AsyncIOScheduler
5. If auto_sync_enabled:
   a. Add incremental sync job: interval, every incremental_interval_minutes
   b. Add full sync job: cron at full_sync_cron_hour:00, misfire_grace_time=None
6. Load NotificationConfig singleton -> evaluation_interval_minutes (default 15)
   a. Add notification_evaluation job: interval, every evaluation_interval_minutes
7. Add Slack scheduled jobs:
   a. scheduled_stale_pr_check: hourly at :05 (checks configured hour at runtime)
   b. scheduled_weekly_digest: hourly at :10 (checks configured day+hour at runtime)
8. scheduler.start(), store in app.state.scheduler
9. yield -> app serves requests
10. On shutdown: scheduler.shutdown(wait=True)

Router registration (main.py):
- All 17 routers get /api prefix
- CORS: allow_origins=[frontend_url], credentials=True, all methods/headers
- Standalone GET /api/health (no auth)
```

## 8. Slack Notification Flow

### Trigger Points

1. **Post-sync** (`github_sync.py`): After sync status determined → `send_sync_notification()` (lazy import, non-blocking)
2. **Daily stale PR check** (APScheduler hourly → `scheduled_stale_pr_check()`): Checks if current UTC hour matches `stale_check_hour_utc` → `send_stale_pr_nudges()`
3. **Weekly digest** (APScheduler hourly → `scheduled_weekly_digest()`): Checks day + hour match → `send_weekly_digest()`

### Notification Delivery (`services/slack.py`)

```
1. Check guards: slack_enabled + bot_token + type-specific toggle
2. For DM types (stale_pr, high_risk_pr, workload, weekly_digest):
   a. Get SlackUserSettings for target developer
   b. Check slack_user_id is set and per-user toggle is enabled
   c. Send via AsyncWebClient.chat_postMessage(channel=slack_user_id)
3. For channel types (sync_complete, sync_failure):
   a. Use config.default_channel
   b. Send via AsyncWebClient.chat_postMessage(channel=default_channel)
4. Log to notification_log (status: sent | failed, error_message if failed)
```

### Configuration

Admin configures via `PATCH /slack/config` (stored in `slack_config` singleton). Each developer configures their Slack user ID and notification preferences via `PATCH /slack/user-settings`. Bot token stored in DB (not env var) for runtime configurability.

## 10. Notification Evaluation Pipeline

**Entry**: `services/notifications.py:evaluate_all_alerts`

### Trigger Points

1. **Scheduled**: APScheduler interval job every `evaluation_interval_minutes` (default 15) → `scheduled_notification_evaluation()` in `main.py`
2. **Post-sync**: `github_sync.py:run_sync()` step 10a → `evaluate_all_alerts(db)` (lazy import, non-blocking — sync completes regardless)
3. **On-demand**: `POST /api/notifications/evaluate` (admin) → `evaluate_all_alerts(db)`

### Evaluation Orchestration

```
1. get_notification_config(db) -> load singleton (id=1), auto-create if missing
2. _get_excluded_developer_ids(db, config.exclude_contribution_categories)
   - Query role_definitions for roles in excluded categories (default: system, non_contributor)
   - Query active developers with those roles -> excluded set
3. For each evaluator in [stale_pr, workload, revert_spike, high_risk_pr,
   collaboration, declining_trend, issue_linkage, ai_budget, sync_failure, config]:
   a. Check per-type enabled toggle
   b. Run evaluator(db, config, excluded_dev_ids) in try/except
      - On failure: log warning, continue to next evaluator
4. db.commit() (single commit for all evaluators)
5. Log active notification count
```

### Per-Evaluator Pattern

Each evaluator follows this pattern:

```
1. Query current state from DB (e.g., open PRs, review counts)
2. Filter out excluded developers
3. For each alert condition met:
   a. Compute alert_key: "{type}:{entity_type}:{entity_id}"
   b. _upsert_notification(db, alert_key, ...) ->
      - SELECT by alert_key (UNIQUE constraint)
      - If exists: update severity/title/body, clear resolved_at if was resolved
      - If new: INSERT Notification row
   c. Add key to active_keys set
4. _auto_resolve_stale(db, alert_type, active_keys) ->
   - SELECT notifications WHERE type=X AND resolved_at IS NULL AND alert_key NOT IN active_keys
   - SET resolved_at = now() on each
```

### Notification Query Flow (`GET /api/notifications`)

```
1. Base query: SELECT notifications WHERE resolved_at IS NULL
2. Apply severity/alert_type filters
3. Load user's reads: SELECT notification_id FROM notification_reads WHERE user_id=X
4. Load user's instance dismissals: SELECT notification_id FROM notification_dismissals
   WHERE user_id=X AND (permanent OR (temporary AND expires_at > now))
5. Load user's type dismissals: SELECT alert_type FROM notification_type_dismissals
   WHERE user_id=X AND (permanent OR (temporary AND expires_at > now))
6. For each notification:
   - is_read = id in read_ids
   - is_dismissed = id in dismissed_ids OR alert_type in dismissed_types
   - Filter out dismissed unless include_dismissed=true
7. Sort: severity priority (critical > warning > info), then newest first
8. Compute: unread_count, counts_by_severity, total
9. Paginate and return NotificationsListResponse
```

## Architectural Concerns

| Severity | Area | Description |
|----------|------|-------------|
| ~~High~~ | ~~AI~~ | ~~`run_one_on_one_prep()` and `run_team_health()` import `get_benchmarks` (renamed)~~ — **Fixed**: Updated to `get_benchmarks_v2` |
| ~~High~~ | ~~Auth~~ | ~~No JWT revocation -- deactivated users retain access up to 7 days~~ — **Fixed**: `get_current_user()` checks `developers.is_active` + `token_version` on every request. Token lifetime reduced to 4 hours. Role changes and deactivation increment `token_version`, immediately invalidating existing JWTs. |
| ~~Medium~~ | ~~Auth~~ | ~~JWT delivered in URL query parameter (`?token=...`) — visible in browser history, server logs, and Referer headers~~ — **Fixed**: Token now delivered in URL fragment (`#token=`), which is never sent to servers or included in Referer headers |
| Medium | Sync | Auto-reactivation in `resolve_author()` / `sync_org_contributors()` can undo manual deactivation -- if the developer appears in GitHub activity or org members during the next sync, `is_active` is silently set back to `True` (warning log only) |
| Medium | Sync | `scheduled_sync()` blocks APScheduler — long-running syncs prevent Slack scheduled jobs from running on time |
| Medium | Sync | Issue comment parent resolution via string-splitting `issue_url` (`split("/")[-1]`) — fragile if GitHub URL format changes |
| Medium | Webhooks | All-or-nothing commit -- failure in any handler rolls back all event processing |
| Medium | Webhooks | Review comments on unknown PRs silently dropped (no retry mechanism) |
| Medium | Webhooks | No dedup/queue -- rapid events on same PR trigger concurrent full re-syncs |
| Medium | Webhooks | `handle_pull_request_review()` calls `recompute_review_quality_tiers()` but not `compute_approval_metrics()` -- approval fields stale until next scheduled sync |
| Medium | Webhooks | Webhook handlers do not trigger `evaluate_all_alerts()` — a PR becoming stale via a webhook event won't generate an alert until the next scheduled evaluation (15 min) or sync |
| ~~Medium~~ | ~~Collaboration~~ | ~~`recompute_collaboration_scores()` always uses last-30-day window~~ — **Fixed**: Uses `since_override` or 90-day window for full syncs |
| ~~Medium~~ | ~~AI~~ | ~~No retry or timeout handling on Claude API calls~~ — **Fixed**: Client uses `max_retries=3` and `timeout=120s` |
| Medium | Goals | Auto-achievement is a write side effect on a GET endpoint |
| Low | Timestamps | `_safe_delta_seconds` / `_to_naive` workarounds for SQLite vs PostgreSQL timezone mismatch |
| ~~Low~~ | ~~Config~~ | ~~Empty `jwt_secret` produces a warning but app starts with insecure signing~~ — **Fixed**: App now exits with fatal error if `JWT_SECRET` is missing or <32 characters |
| Low | Auth | No JWT refresh mechanism — users must re-authenticate every 4 hours via full OAuth flow |
| Medium | Notifications | `evaluate_all_alerts()` returns a `counts` dict initialized to zeros but never populated — result is always `{"created": 0, "updated": 0, "resolved": 0}` regardless of actual work done |
| Medium | Notifications | `get_active_notifications()` loads ALL active notifications into memory before filtering/paginating — no SQL-level pagination; will degrade with large notification volumes |
| Low | Notifications | `notification_evaluation` scheduler interval loaded once at startup from `notification_config.evaluation_interval_minutes` — updating config via API does not reschedule the job (requires restart) |
