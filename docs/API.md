# DevPulse API Reference

Base URL: `http://localhost:8000/api`

## Authentication

DevPulse uses GitHub OAuth for authentication. After login, all protected endpoints require a JWT:
```
Authorization: Bearer {jwt_token}
```

Every authenticated request checks `developers.is_active` and `token_version` in the database. Deactivated or deleted accounts receive `401 Unauthorized` immediately, even if the JWT is otherwise valid. Tokens whose `token_version` does not match the database value are also rejected with `401` — this happens after role changes or deactivation, which increment the version and invalidate all existing JWTs for that user. Token lifetime is 4 hours.

**Two roles:**
- `admin` — full access to all endpoints
- `developer` — read-only access to own stats, profile, goals, and repo stats

**Public endpoints** (no auth required): `GET /api/health`, `POST /api/webhooks/github`, `GET /api/auth/login`, `GET /api/auth/callback`, `POST /api/logs/ingest`

### Access Control Summary

| Endpoint Group | Admin | Developer |
|----------------|-------|-----------|
| **Auth** (`/api/auth/*`) | Public | Public |
| **Developer stats** (`/api/stats/developer/{id}`) | Any ID | Own ID only |
| **Developer trends** (`/api/stats/developer/{id}/trends`) | Any ID | Own ID only |
| **Team/benchmarks/workload/collaboration/collaboration-trends/collaboration-pair/stale-prs/issue-linkage/issue-quality/issue-creators** | Yes | No (403) |
| **Code churn** (`/api/stats/repo/{id}/churn`) | Yes | No (403) |
| **PR risk** (`/api/stats/pr/{id}/risk`, `/api/stats/risk-summary`) | Yes | No (403) |
| **CI/CD stats** (`/api/stats/ci`) | Yes | No (403) |
| **Repo stats** (`/api/stats/repo/{id}`) | Yes | Yes |
| **Developer relationships** (`/api/developers/{id}/relationships`) | Full CRUD | GET own only |
| **Developer works-with** (`/api/developers/{id}/works-with`) | Any ID | Own ID only |
| **Org tree** (`/api/org-tree`) | Yes | No (403) |
| **Over-tagged / communication scores** (`/api/stats/over-tagged`, `/api/stats/communication-scores`) | Yes | No (403) |
| **Developers CRUD** (`/api/developers/*`) | Full access | GET own profile only |
| **Activity summary** (`/api/developers/{id}/activity-summary`) | Any ID | Own ID only |
| **Roles** (`/api/roles`) | Full CRUD | GET (list) only |
| **Goals** (`/api/goals/*`) | Full access | GET own goals, POST/PATCH self-goals |
| **Goal progress** (`/api/goals/{id}/progress`) | Any goal | Own goals only |
| **Sync** (`/api/sync/*`) | Yes | No (403) |
| **AI Analysis** (`/api/ai/*`) | Yes | No (403) |
| **Slack config/test/history** (`/api/slack/config`, `/test`, `/notifications`) | Yes | No (403) |
| **Slack user settings** (`/api/slack/user-settings`) | Own + any (admin) | Own only |
| **Notifications** (`/api/notifications`, `/read`, `/dismiss`, `/config`, `/evaluate`) | Yes | No (403) |
| **Log ingestion** (`/api/logs/ingest`) | Public | Public |

Date parameters accept ISO 8601 format: `2026-01-01T00:00:00Z`. When `date_from`/`date_to` are omitted, defaults to the last 30 days.

### Rate Limiting

All endpoints are rate-limited by client IP (X-Forwarded-For–aware). Exceeding the limit returns `429 Too Many Requests`.

| Endpoint | Limit |
|----------|-------|
| `POST /api/logs/ingest` | 10/minute |
| `GET /api/auth/login` | 10/minute |
| `GET /api/auth/callback` | 10/minute |
| `POST /api/webhooks/github` | 60/minute |
| `POST /api/sync/start` | 5/minute |
| `POST /api/notifications/evaluate` | 5/minute |
| `POST /api/work-categories/reclassify` | 2/minute |
| All other routes | 120/minute |

Rate limiting can be disabled via `RATE_LIMIT_ENABLED=false` environment variable.

---

## Auth

### GET /api/auth/login

Returns the GitHub OAuth authorization URL. The frontend should redirect the user to this URL.

**Response:** `200 OK`
```json
{
  "url": "https://github.com/login/oauth/authorize?client_id=...&redirect_uri=...&scope=read:user"
}
```

### GET /api/auth/callback?code={code}

OAuth callback. Exchanges the GitHub authorization code for an access token, fetches user profile, creates or updates the developer record, and issues a JWT.

**Behavior:**
- New user → creates developer record (`app_role: "developer"`, or `"admin"` if username matches `DEVPULSE_INITIAL_ADMIN` **and** no admin exists yet)
- Existing user → updates `avatar_url`
- Deactivated user → returns `403 Forbidden`

**Response:** `302 Redirect` to `{FRONTEND_URL}/auth/callback#token={jwt}` (token in URL fragment, not query parameter)

### GET /api/auth/me

Returns the currently authenticated user's info.

**Response:** `200 OK`
```json
{
  "developer_id": 1,
  "github_username": "octocat",
  "display_name": "Octo Cat",
  "app_role": "admin",
  "avatar_url": "https://avatars.githubusercontent.com/u/583231"
}
```

---

## Health

### GET /api/health

Returns service status. No authentication required.

**Response:** `200 OK`
```json
{ "status": "ok" }
```

---

## Developers

Team registry CRUD. Developers are the core entity linking GitHub usernames to internal profiles.

**Access:** Admin-only for list, create, update, delete. Developers can GET their own profile.

**DeveloperResponse** includes `app_role` field (`"admin"` or `"developer"`).

### GET /api/developers

List developers. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter by team name |
| `is_active` | bool | `true` | Filter by active status |

**Response:** `200 OK` — `DeveloperResponse[]` ordered by `display_name`

### POST /api/developers

Create a developer. **Admin only.**

**Request Body:**
```json
{
  "github_username": "octocat",
  "display_name": "Octo Cat",
  "email": "octo@example.com",
  "role": "developer",
  "skills": ["python", "react"],
  "specialty": "backend",
  "location": "San Francisco",
  "timezone": "America/Los_Angeles",
  "team": "Platform",
  "notes": "Started Q1 2026"
}
```

`role` must be a valid `role_key` from `GET /api/roles`. 15 default roles are seeded (see [Roles](#roles) section). Returns `400` if the role doesn't exist.

**Response:** `201 Created` — `DeveloperResponse`

**Errors:**
- `400 Bad Request` if `role` is not a valid role_key
- `409 Conflict` if `github_username` exists and is active (plain string detail)
- `409 Conflict` if `github_username` exists but is inactive (structured detail for reactivation prompt):
```json
{
  "detail": {
    "code": "inactive_exists",
    "developer_id": 42,
    "display_name": "Octo Cat"
  }
}
```

### GET /api/developers/{developer_id}

**Access:** Admin can view any developer. Developers can view their own profile only.

**Response:** `200 OK` — `DeveloperResponse`
**Errors:** `404 Not Found`, `403 Forbidden` (developer accessing another profile)

### PATCH /api/developers/{developer_id}

Partial update. Only provided fields are changed. **Admin only.**

**Request Body:** Any subset of `DeveloperCreate` fields (except `github_username`), plus:
- `app_role`: `"admin"` or `"developer"` — promotes or demotes a user
- `is_active`: `true` or `false` — activates or deactivates a developer

Changing `app_role` or `is_active` increments `token_version`, which invalidates all existing JWTs for that developer (forcing re-authentication).

**Response:** `200 OK` — `DeveloperResponse`

### GET /api/developers/{developer_id}/deactivation-impact

Returns a summary of open work assigned to a developer, useful before deactivation to identify items that may need reassignment. **Admin only.**

**Response:** `200 OK`
```json
{
  "open_prs": 3,
  "open_issues": 1,
  "open_branches": ["feature/auth-v2", "fix/rate-limit", "refactor/sync"]
}
```

Draft PRs are excluded from `open_prs` and `open_branches`. Branches are derived from `head_branch` of open non-draft PRs. Works on both active and inactive developers — calling it on an already-inactive developer returns any open work still associated with their ID.

**Errors:** `404 Not Found`

### GET /api/developers/{developer_id}/activity-summary

Returns all-time (lifetime) activity statistics for a developer, useful for identifying junk/duplicate accounts or understanding overall contribution patterns. No date range filtering — always returns totals across all synced data. **Admin or own profile.**

**Response:** `200 OK`
```json
{
  "prs_authored": 142,
  "prs_merged": 128,
  "prs_open": 3,
  "reviews_given": 310,
  "issues_created": 45,
  "issues_assigned": 67,
  "repos_touched": 8,
  "first_activity": "2024-03-15T09:22:00Z",
  "last_activity": "2026-03-28T14:10:00Z",
  "work_categories": {
    "feature": 72,
    "bugfix": 38,
    "tech_debt": 12,
    "ops": 4,
    "unknown": 2
  }
}
```

`repos_touched` counts distinct repositories where the developer authored PRs or submitted reviews. `first_activity` / `last_activity` are the earliest/latest timestamps across authored PRs and submitted reviews. `work_categories` shows the breakdown of merged PRs by work category (feature/bugfix/tech_debt/ops/unknown), using stored `work_category` when available and falling back to label/title-based classification via `classify_work_item()`.

A developer with zero activity returns all zeros, null dates, and an empty `work_categories` object.

**Errors:** `403 Forbidden` (non-admin viewing another developer), `404 Not Found`

### DELETE /api/developers/{developer_id}

Soft-delete: sets `is_active = false` and increments `token_version` (invalidating existing JWTs). **Admin only.** Deactivated developers cannot log in via OAuth.

Mechanically identical to `PATCH { is_active: false }` — both set `is_active = false` and increment `token_version`. The convention is to use `PATCH` for standard deactivation (goes through `DeactivateDialog` with the impact check) and `DELETE` for removing junk/system accounts.

**Response:** `204 No Content`

---

## Roles

Role definitions are admin-configurable. Each role maps to a fixed **contribution category** that controls how the role participates in statistics:

| Category | Stats behavior |
|----------|---------------|
| `code_contributor` | Included in PR/review benchmarks and percentile calculations |
| `issue_contributor` | Excluded from code benchmarks; included in issue creator stats |
| `non_contributor` | Excluded from all benchmarks |
| `system` | Excluded from everything |

15 default roles are seeded by migration. Admins can create additional custom roles.

### GET /api/roles

List all role definitions, ordered by `display_order`. **Any authenticated user.**

**Response:** `200 OK`
```json
[
  {
    "role_key": "developer",
    "display_name": "Developer",
    "contribution_category": "code_contributor",
    "display_order": 1,
    "is_default": true
  },
  {
    "role_key": "product_manager",
    "display_name": "Product Manager",
    "contribution_category": "issue_contributor",
    "display_order": 8,
    "is_default": true
  }
]
```

### POST /api/roles

Create a custom role definition. **Admin only.**

**Request body:**
```json
{
  "role_key": "data_scientist",
  "display_name": "Data Scientist",
  "contribution_category": "code_contributor"
}
```

`role_key` must be lowercase alphanumeric with underscores, 2-49 chars, starting with a letter.

**Response:** `201 Created` — returns the created `RoleDefinition`.

**Errors:**
- `409` — role_key already exists or invalid format

### PATCH /api/roles/{role_key}

Update a role definition (display name, contribution category, display order). **Admin only.**

**Request body:** (all fields optional)
```json
{
  "display_name": "Senior Data Scientist",
  "contribution_category": "issue_contributor",
  "display_order": 14
}
```

**Response:** `200 OK` — returns the updated `RoleDefinition`.

**Errors:**
- `404` — role_key not found

### DELETE /api/roles/{role_key}

Delete a custom role definition. **Admin only.**

Cannot delete default roles (`is_default = true`) or roles currently assigned to any developer.

**Response:** `204 No Content`

**Errors:**
- `409` — role is a default role, or role is still assigned to developers

---

## Stats

All stats endpoints accept optional `date_from` and `date_to` query parameters.

### GET /api/stats/developer/{developer_id}

Developer metrics for a date range. **Developers can only access their own stats.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |
| `include_percentiles` | bool | `false` | Include team-relative percentile placement |

**Response:** `200 OK`
```json
{
  "prs_opened": 12,
  "prs_merged": 10,
  "prs_closed_without_merge": 1,
  "prs_open": 3,
  "prs_draft": 1,
  "total_additions": 2450,
  "total_deletions": 890,
  "total_changed_files": 45,
  "reviews_given": {
    "approved": 8,
    "changes_requested": 3,
    "commented": 5
  },
  "reviews_received": 15,
  "review_quality_breakdown": {
    "rubber_stamp": 2,
    "minimal": 3,
    "standard": 6,
    "thorough": 5
  },
  "review_quality_score": 6.25,
  "avg_time_to_first_review_hours": 4.2,
  "avg_time_to_merge_hours": 18.5,
  "issues_assigned": 5,
  "issues_closed": 3,
  "avg_time_to_close_issue_hours": 48.0,
  "avg_time_to_approve_hours": 6.8,
  "avg_time_after_approve_hours": 2.1,
  "prs_merged_without_approval": 1,
  "avg_review_rounds": 1.4,
  "prs_merged_first_pass": 7,
  "first_pass_rate": 70.0,
  "prs_self_merged": 2,
  "self_merge_rate": 20.0,
  "prs_reverted": 0,
  "reverts_authored": 0,
  "prs_linked_to_issue": 8,
  "issue_linkage_rate": 0.6667,
  "comment_type_distribution": {
    "nit": 8,
    "blocker": 2,
    "suggestion": 5,
    "question": 3,
    "architectural": 1,
    "praise": 4,
    "general": 12
  },
  "nit_ratio": 0.2286,
  "blocker_catch_rate": 0.125
}
```

**Issue linkage fields:**
- `prs_linked_to_issue` — count of PRs authored by this developer that contain closing keywords (`Closes #N`, `Fixes #N`, etc.) linking them to issues
- `issue_linkage_rate` — fraction of PRs linked to issues (`prs_linked_to_issue / prs_opened`). `null` if no PRs opened

**Comment type fields:**
- `comment_type_distribution` — counts of review comments by type (as reviewer). Types: `nit`, `blocker`, `architectural`, `question`, `praise`, `suggestion`, `general`. Empty `{}` if no comments.
- `nit_ratio` — fraction of all review comments that are nits (`nit_count / total_comments`). `null` if no comments.
- `blocker_catch_rate` — fraction of reviews that contain at least one blocker comment (`reviews_with_blocker / total_reviews_given`). `null` if no reviews given.

When `include_percentiles=true`, adds:
```json
{
  "percentiles": {
    "time_to_merge_h": {
      "value": 18.5,
      "percentile_band": "p50_to_p75",
      "team_median": 22.0
    },
    "prs_merged": {
      "value": 10.0,
      "percentile_band": "above_p75",
      "team_median": 7.0
    }
  }
}
```

Percentile bands: `below_p25`, `p25_to_p50`, `p50_to_p75`, `above_p75`. For lower-is-better metrics (time_to_merge_h, time_to_first_review_h, review_turnaround_h), bands are inverted so `above_p75` always means "best performer."

### GET /api/stats/team

Team-wide aggregate metrics. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |
| `team` | string | - | Filter by team name (all active devs if omitted) |

**Response:** `200 OK`
```json
{
  "developer_count": 12,
  "total_prs": 85,
  "total_merged": 72,
  "merge_rate": 84.7,
  "avg_time_to_first_review_hours": 3.8,
  "avg_time_to_merge_hours": 16.2,
  "total_reviews": 210,
  "total_issues_closed": 34,
  "avg_review_rounds": 1.6,
  "first_pass_rate": 65.0,
  "revert_rate": 2.5
}
```

### GET /api/stats/repos/summary

Batch per-repo metrics for all tracked repositories. Returns current-period and previous-period values for trend computation. Uses efficient GROUP BY queries (6 total, not per-repo).

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |

**Response:** `200 OK` — `RepoSummaryItem[]`
```json
[
  {
    "repo_id": 1,
    "total_prs": 34,
    "total_merged": 28,
    "total_issues": 15,
    "total_reviews": 72,
    "avg_time_to_merge_hours": 8.4,
    "last_pr_date": "2026-03-28T14:30:00Z",
    "prev_total_prs": 30,
    "prev_total_merged": 25,
    "prev_avg_time_to_merge_hours": 9.1
  }
]
```

| Field | Description |
|-------|-------------|
| `repo_id` | Repository ID |
| `total_prs` | PRs created in current period |
| `total_merged` | PRs merged in current period |
| `total_issues` | Issues created in current period |
| `total_reviews` | Reviews submitted in current period |
| `avg_time_to_merge_hours` | Average merge time for merged PRs in current period (null if no merges) |
| `last_pr_date` | Most recent PR created_at in current period (null if no PRs) |
| `prev_total_prs` | PRs created in previous period (same duration, shifted back) |
| `prev_total_merged` | PRs merged in previous period |
| `prev_avg_time_to_merge_hours` | Average merge time in previous period (null if no merges) |

Only tracked repos are included. Previous period = `[date_from - period_length, date_from]`. Repos with no activity in either period still appear in the response with zero/null values. Auth: any authenticated user (not admin-only).

### GET /api/stats/repo/{repo_id}

Repository-scoped metrics with top contributors.

**Response:** `200 OK`
```json
{
  "total_prs": 45,
  "total_merged": 38,
  "total_issues": 22,
  "total_issues_closed": 18,
  "total_reviews": 95,
  "avg_time_to_merge_hours": 14.3,
  "top_contributors": [
    { "developer_id": 1, "github_username": "octocat", "display_name": "Octo Cat", "pr_count": 12 }
  ]
}
```

### GET /api/stats/repo/{repo_id}/churn

File-level code churn analysis for a repository. Identifies hotspot files (frequently modified) and stale directories (no PR activity in period). **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |
| `limit` | int (1-200) | `50` | Max hotspot files to return |

**Response:** `200 OK`
```json
{
  "repo_id": 1,
  "repo_name": "my-service",
  "hotspot_files": [
    {
      "path": "src/main.py",
      "change_frequency": 8,
      "total_additions": 342,
      "total_deletions": 128,
      "total_churn": 470,
      "contributor_count": 3,
      "last_modified_at": "2026-03-25T14:30:00Z"
    }
  ],
  "stale_directories": [
    {
      "path": "legacy",
      "file_count": 12,
      "last_pr_activity": "2025-11-01T10:00:00Z"
    },
    {
      "path": "vendor",
      "file_count": 45,
      "last_pr_activity": null
    }
  ],
  "total_files_in_repo": 250,
  "total_files_changed": 42,
  "tree_truncated": false
}
```

| Field | Description |
|-------|-------------|
| `hotspot_files` | Top N files by change frequency (distinct PRs), with churn volume and contributor count |
| `stale_directories` | Top-level directories with zero PR activity in the date range. `last_pr_activity` is the most recent PR touching any file under that dir (all time), or `null` if never touched |
| `total_files_in_repo` | Count of files in the repo tree snapshot (from GitHub Trees API) |
| `total_files_changed` | Distinct files modified by PRs in the period |
| `tree_truncated` | `true` if GitHub truncated the tree response (>100K entries) |

### GET /api/stats/benchmark-groups

List all configured benchmark peer groups. **Admin only.**

**Response:** `200 OK`
```json
[
  {
    "group_key": "ics",
    "display_name": "IC Engineers",
    "display_order": 1,
    "roles": ["developer", "senior_developer", "architect", "intern"],
    "metrics": ["prs_merged", "time_to_merge_h", "time_to_first_review_h", "time_to_approve_h", "time_after_approve_h", "additions_per_pr", "review_rounds"],
    "min_team_size": 3,
    "is_default": true
  }
]
```

### PATCH /api/stats/benchmark-groups/{group_key}

Update a benchmark group's configuration. **Admin only.** All fields optional.

**Request body:**
```json
{
  "display_name": "Senior Engineers",
  "roles": ["senior_developer", "architect"],
  "metrics": ["prs_merged", "time_to_merge_h"],
  "min_team_size": 2
}
```

**Response:** `200 OK` — Updated `BenchmarkGroupResponse`.
**Errors:** `400` if role names not found in `role_definitions` table, invalid metric keys, or empty metrics list.

### GET /api/stats/benchmarks

Role-based peer group benchmarks with per-developer metrics, percentile bands, and team comparison. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `group` | string | first group by display_order | Benchmark group key (e.g., `ics`, `leads`, `qa`) |
| `team` | string | - | Filter developers by team name |
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |

**Response:** `200 OK`
```json
{
  "group": {
    "group_key": "ics",
    "display_name": "IC Engineers",
    "display_order": 1,
    "roles": ["developer", "senior_developer", "architect", "intern"],
    "metrics": ["prs_merged", "time_to_merge_h", "reviews_given"],
    "min_team_size": 3,
    "is_default": true
  },
  "period_start": "2026-02-26T00:00:00Z",
  "period_end": "2026-03-28T00:00:00Z",
  "sample_size": 12,
  "team": null,
  "metrics": {
    "prs_merged": { "p25": 3.0, "p50": 7.0, "p75": 12.0 },
    "time_to_merge_h": { "p25": 8.5, "p50": 16.2, "p75": 28.0 },
    "reviews_given": { "p25": 4.0, "p50": 10.0, "p75": 18.0 }
  },
  "metric_info": [
    { "key": "prs_merged", "label": "PRs Merged", "lower_is_better": false, "unit": "count" },
    { "key": "time_to_merge_h", "label": "Time to Merge", "lower_is_better": true, "unit": "hours" },
    { "key": "reviews_given", "label": "Reviews Given", "lower_is_better": false, "unit": "count" }
  ],
  "developers": [
    {
      "developer_id": 1,
      "display_name": "Alice",
      "avatar_url": "https://avatars.githubusercontent.com/u/1",
      "team": "backend",
      "role": "senior_developer",
      "metrics": {
        "prs_merged": { "value": 10.0, "percentile_band": "p50_to_p75" },
        "time_to_merge_h": { "value": 12.5, "percentile_band": "p50_to_p75" },
        "reviews_given": { "value": 15.0, "percentile_band": "p50_to_p75" }
      }
    }
  ],
  "team_comparison": [
    { "team": "backend", "sample_size": 5, "metrics": { "prs_merged": 8.0, "time_to_merge_h": 14.0, "reviews_given": 12.0 } },
    { "team": "frontend", "sample_size": 4, "metrics": { "prs_merged": 6.0, "time_to_merge_h": 20.0, "reviews_given": 8.0 } }
  ]
}
```

**Notes:**
- Developers with `role=system_account` or `role=NULL` are excluded from all groups.
- `team_comparison` is `null` when a specific team is filtered, or fewer than 2 teams meet `min_team_size`.
- Percentile bands: `below_p25`, `p25_to_p50`, `p50_to_p75`, `above_p75`. For lower-is-better metrics, `above_p75` means "best" (lowest value).
- Available metric keys: `prs_merged`, `time_to_merge_h`, `time_to_first_review_h`, `time_to_approve_h`, `time_after_approve_h`, `reviews_given`, `review_turnaround_h`, `additions_per_pr`, `review_rounds`, `review_quality_score`, `changes_requested_rate`, `blocker_catch_rate`, `issues_closed`, `prs_merged_bugfix`.

### GET /api/developers/unassigned-role-count

Count of active developers with no role assigned. **Any authenticated user.**

**Response:** `200 OK`
```json
{ "count": 7 }
```

### GET /api/stats/developer/{developer_id}/trends

Period-bucketed stats with linear regression trend analysis. **Developers can only access their own trends.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `periods` | int (2-52) | `8` | Number of time buckets |
| `period_type` | string | `week` | `week`, `sprint`, or `month` |
| `sprint_length_days` | int (7-28) | `14` | Only used when `period_type=sprint` |

**Response:** `200 OK`
```json
{
  "developer_id": 1,
  "period_type": "week",
  "periods": [
    {
      "start": "2026-02-05T00:00:00Z",
      "end": "2026-02-12T00:00:00Z",
      "prs_merged": 3,
      "avg_time_to_merge_h": 12.5,
      "reviews_given": 5,
      "additions": 450,
      "deletions": 120,
      "issues_closed": 1
    }
  ],
  "trends": {
    "prs_merged": { "direction": "improving", "change_pct": 15.2 },
    "avg_time_to_merge_h": { "direction": "stable", "change_pct": -2.1 },
    "reviews_given": { "direction": "worsening", "change_pct": -22.0 }
  }
}
```

Direction respects metric polarity: decreasing `avg_time_to_merge_h` = "improving". Change < 5% = "stable". Neutral metrics (additions, deletions) always show "stable."

### GET /api/stats/collaboration

Reviewer-author collaboration matrix with team insights. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter by team |

**Response:** `200 OK`
```json
{
  "matrix": [
    {
      "reviewer_id": 1, "reviewer_name": "Alice", "reviewer_team": "Platform",
      "author_id": 2, "author_name": "Bob", "author_team": "Platform",
      "reviews_count": 12, "approvals": 8, "changes_requested": 4
    }
  ],
  "insights": {
    "silos": [
      { "team_a": "Platform", "team_b": "Mobile", "note": "Zero cross-team reviews" }
    ],
    "bus_factors": [
      { "repo_name": "org/core-api", "sole_reviewer_id": 1, "sole_reviewer_name": "Alice", "review_share_pct": 78.5 }
    ],
    "isolated_developers": [
      { "developer_id": 5, "display_name": "Charlie" }
    ],
    "strongest_pairs": []
  }
}
```

Insights:
- **Silos:** Team pairs with zero cross-team reviews (excludes devs with no team set)
- **Bus factors:** Reviewers with >70% of all reviews on a repo in the date range
- **Isolated:** Developers with 0 reviews given AND reviews received from <= 1 unique reviewer
- **Strongest pairs:** Top 10 mutual review pairs by combined review count

### GET /api/stats/collaboration/trends

Monthly bus factor, silo, and isolation counts over time. Divides the date range into monthly buckets and computes collaboration health indicators per bucket. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter by team |
| `date_from` | datetime | 30 days ago | Start of date range |
| `date_to` | datetime | now | End of date range |

**Response:** `200 OK`
```json
{
  "periods": [
    {
      "period_start": "2025-01-01T00:00:00",
      "period_end": "2025-02-01T00:00:00",
      "period_label": "2025-01",
      "bus_factor_count": 2,
      "silo_count": 1,
      "isolated_developer_count": 3
    },
    {
      "period_start": "2025-02-01T00:00:00",
      "period_end": "2025-03-01T00:00:00",
      "period_label": "2025-02",
      "bus_factor_count": 1,
      "silo_count": 0,
      "isolated_developer_count": 2
    }
  ]
}
```

Implementation details:
- Fetches all reviews in the full date range with a single query, then buckets in Python — 2 DB queries total regardless of period count
- **Bus factor:** Repos where one reviewer handles >70% of reviews in the bucket
- **Silo:** Team pairs with zero cross-team reviews in the bucket. Returns 0 (not the total possible pairs) when a bucket has no review activity to avoid misleading spikes
- **Isolated:** Developers who gave 0 reviews AND received reviews from <= 1 unique reviewer. Returns 0 when a bucket has no review activity

### GET /api/stats/collaboration/pair

Detailed review interaction between a specific reviewer→author pair, including relationship classification. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `reviewer_id` | int | **required** | Reviewer developer ID |
| `author_id` | int | **required** | PR author developer ID |
| `date_from` | datetime | 30 days ago | Start of date range |
| `date_to` | datetime | now | End of date range |

**Response:** `200 OK`
```json
{
  "reviewer_id": 1,
  "reviewer_name": "Alice",
  "reviewer_avatar_url": "https://avatars.githubusercontent.com/u/123",
  "reviewer_team": "Platform",
  "author_id": 2,
  "author_name": "Bob",
  "author_avatar_url": "https://avatars.githubusercontent.com/u/456",
  "author_team": "Backend",
  "total_reviews": 15,
  "approval_rate": 0.667,
  "changes_requested_rate": 0.2,
  "avg_quality_tier": "standard",
  "quality_tier_breakdown": [
    { "tier": "standard", "count": 8 },
    { "tier": "thorough", "count": 5 },
    { "tier": "minimal", "count": 2 }
  ],
  "comment_type_breakdown": [
    { "comment_type": "architectural", "count": 6 },
    { "comment_type": "suggestion", "count": 4 },
    { "comment_type": "blocker", "count": 3 },
    { "comment_type": "nit", "count": 2 }
  ],
  "total_comments": 15,
  "relationship": {
    "label": "mentor",
    "confidence": 0.85,
    "explanation": "Heavily one-directional reviews with substantive architectural/blocker feedback and high review quality — consistent with a mentoring relationship."
  },
  "recent_prs": [
    {
      "pr_id": 42,
      "pr_number": 301,
      "title": "Refactor auth middleware",
      "html_url": "https://github.com/org/repo/pull/301",
      "repo_full_name": "org/repo",
      "review_state": "APPROVED",
      "quality_tier": "thorough",
      "comment_count": 3,
      "additions": 120,
      "deletions": 45,
      "submitted_at": "2025-03-15T14:30:00Z"
    }
  ]
}
```

**Relationship labels:** `mentor` (asymmetric + substantive comments + high quality), `peer` (balanced bidirectional), `gatekeeper` (asymmetric + high changes_requested), `rubber_stamp` (high approval + low quality + few comments), `one_way_dependency` (asymmetric, no mentor/gatekeeper signals), `casual` (< 3 reviews), `none` (0 reviews).

**Error responses:**
- `404` — reviewer or author developer ID not found
- `403` — non-admin user

Implementation details:
- 3 SQL queries: reviews+PRs joined, comment type aggregation by reviewer username, reverse review count for relationship asymmetry detection
- Recent PRs deduplicated by PR ID (takes most recent review per PR), capped at 30
- `classify_pair_relationship()` is a pure function with clear input/output contract designed for future AI classifier swap

### GET /api/stats/workload

Per-developer workload indicators and automated alerts. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter by team |

**Response:** `200 OK`
```json
{
  "developers": [
    {
      "developer_id": 1,
      "github_username": "octocat",
      "display_name": "Octo Cat",
      "open_prs_authored": 3,
      "drafts_open": 1,
      "open_prs_reviewing": 2,
      "open_issues_assigned": 1,
      "reviews_given_this_period": 8,
      "reviews_received_this_period": 5,
      "prs_waiting_for_review": 1,
      "avg_review_wait_h": 6.5,
      "workload_score": "balanced"
    }
  ],
  "alerts": [
    { "type": "review_bottleneck", "developer_id": 3, "message": "Alice gave 25 reviews (team median: 10)" },
    { "type": "stale_prs", "developer_id": 2, "message": "PR #42 (Fix auth) waiting for review > 48h" },
    { "type": "uneven_assignment", "developer_id": null, "message": "Top 2 dev(s) hold 15/20 open issues" },
    { "type": "underutilized", "developer_id": 5, "message": "Charlie has 0 PRs and 0 reviews in the period" }
  ]
}
```

Workload scores: `low` (no activity), `balanced` (<= 5 total load), `high` (<= 12), `overloaded` (> 12). Total load = open PRs authored + open PRs reviewing + open issues assigned. Completed reviews are excluded from the score calculation.

### GET /api/stats/stale-prs

Open PRs that need attention, sorted by staleness (most stale first). **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter by team (PRs authored by team members) |
| `threshold_hours` | int (1-720) | `24` | Minimum age in hours before a PR is considered stale |

**Three staleness categories:**
1. **`no_review`** — open, non-draft, no first review received, older than threshold
2. **`changes_requested_no_response`** — most recent review is `CHANGES_REQUESTED`, author hasn't updated the PR since (within 1h tolerance), review older than threshold
3. **`approved_not_merged`** — has at least one `APPROVED` review, last approval older than threshold, still not merged

PRs are deduplicated across categories (priority: no_review > changes_requested > approved_not_merged).

**Response:** `200 OK`
```json
{
  "stale_prs": [
    {
      "pr_id": 42,
      "number": 123,
      "title": "Fix authentication middleware",
      "html_url": "https://github.com/org/repo/pull/123",
      "repo_name": "org/repo",
      "author_name": "Alice",
      "author_id": 1,
      "age_hours": 72.5,
      "is_draft": false,
      "review_count": 0,
      "has_approved": false,
      "has_changes_requested": false,
      "last_activity_at": "2026-03-25T10:00:00Z",
      "stale_reason": "no_review"
    },
    {
      "pr_id": 55,
      "number": 145,
      "title": "Update caching layer",
      "html_url": "https://github.com/org/repo/pull/145",
      "repo_name": "org/repo",
      "author_name": "Bob",
      "author_id": 2,
      "age_hours": 48.2,
      "is_draft": false,
      "review_count": 1,
      "has_approved": true,
      "has_changes_requested": false,
      "last_activity_at": "2026-03-26T08:30:00Z",
      "stale_reason": "approved_not_merged"
    }
  ],
  "total_count": 2
}
```

---

### GET /api/stats/issue-linkage

Issue-to-PR linkage statistics via closing keywords parsed from PR bodies. Shows how well issues are connected to the PRs that resolved them. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Start of date range (ISO 8601) |
| `date_to` | datetime | now | End of date range (ISO 8601) |
| `team` | string | - | Filter by team (PRs by author team, issues by assignee team) |

**Closing keywords recognized:** `close`, `closes`, `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, `resolved` — case-insensitive, followed by `#N` where N is an issue number in the same repo.

**Response:** `200 OK`
```json
{
  "issues_with_linked_prs": 15,
  "issues_without_linked_prs": 3,
  "avg_prs_per_issue": 1.2,
  "issues_with_multiple_prs": 2,
  "prs_without_linked_issues": 8
}
```

| Field | Description |
|-------|-------------|
| `issues_with_linked_prs` | Closed issues referenced by at least one PR's closing keywords |
| `issues_without_linked_prs` | Closed issues with no PR referencing them (work outside PR process) |
| `avg_prs_per_issue` | Average PRs per linked issue (`null` if no linked issues) |
| `issues_with_multiple_prs` | Issues linked to 2+ PRs (may indicate scope was too large) |
| `prs_without_linked_issues` | PRs in the date range that don't reference any issue (undocumented work) |

---

### GET /api/stats/issue-linkage/developers

Per-developer PR-to-issue linkage breakdown. Shows each developer's linkage rate and flags those below the attention threshold. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Start of date range (ISO 8601) |
| `date_to` | datetime | now | End of date range (ISO 8601) |
| `team` | string | - | Filter by team |

**Response:** `200 OK`
```json
{
  "developers": [
    {
      "developer_id": 5,
      "github_username": "alice",
      "display_name": "Alice Chen",
      "team": "backend",
      "prs_total": 12,
      "prs_linked": 2,
      "linkage_rate": 0.1667
    },
    {
      "developer_id": 3,
      "github_username": "bob",
      "display_name": "Bob Smith",
      "team": "platform",
      "prs_total": 8,
      "prs_linked": 7,
      "linkage_rate": 0.875
    }
  ],
  "team_average_rate": 0.45,
  "attention_threshold": 0.2,
  "attention_developers": [
    {
      "developer_id": 5,
      "github_username": "alice",
      "display_name": "Alice Chen",
      "team": "backend",
      "prs_total": 12,
      "prs_linked": 2,
      "linkage_rate": 0.1667
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `developers` | All active developers with at least 1 PR, sorted by `linkage_rate` ascending (worst first) |
| `team_average_rate` | Overall linkage rate across all developers in the result set |
| `attention_threshold` | Rate threshold below which developers are flagged (default `0.2` = 20%) |
| `attention_developers` | Subset of `developers` with `linkage_rate < attention_threshold` |
| `linkage_rate` | Fraction of the developer's PRs that contain closing keywords (0.0–1.0) |

Only developers with at least 1 PR in the date range are included. Linkage is determined by the same closing keyword regex as `GET /stats/issue-linkage`.

---

### GET /api/stats/issues/quality

Issue quality scoring statistics. Identifies poorly-defined tasks by analyzing body content, checklist usage, comment activity, closure reasons, and reopen patterns. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Start of date range (ISO 8601) |
| `date_to` | datetime | now | End of date range (ISO 8601) |
| `team` | string | - | Filter by team (issues by assignee team) |

**Note:** Filters by `created_at` (issues created in period). Team filter uses `assignee_id` — unassigned issues are only included in unfiltered queries.

**Response:** `200 OK`
```json
{
  "total_issues_created": 42,
  "avg_body_length": 312.5,
  "pct_with_checklist": 28.6,
  "avg_comment_count": 3.2,
  "pct_closed_not_planned": 12.5,
  "avg_reopen_count": 0.15,
  "issues_without_body": 8,
  "label_distribution": {
    "bug": 15,
    "feature": 12,
    "tech-debt": 5,
    "documentation": 3
  }
}
```

| Field | Description |
|-------|-------------|
| `total_issues_created` | Total issues created in the date range |
| `avg_body_length` | Average character count of issue bodies |
| `pct_with_checklist` | Percentage of issues containing `- [ ]` or `- [x]`/`- [X]` task list syntax |
| `avg_comment_count` | Average GitHub comment count per issue (from API `comments` field) |
| `pct_closed_not_planned` | Percentage of closed issues with `state_reason == "not_planned"` (out of all closed issues in range) |
| `avg_reopen_count` | Average number of times issues were reopened (closed→open transitions) |
| `issues_without_body` | Count of issues with body length < 50 characters (empty or minimal description) |
| `label_distribution` | Map of label name → count across all issues in range |

---

### GET /api/stats/issues/labels

Label distribution across issues created in the date range. Returns a flat map of label names to their occurrence count. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Start of date range (ISO 8601) |
| `date_to` | datetime | now | End of date range (ISO 8601) |
| `team` | string | - | Filter by team (issues by assignee team) |

**Response:** `200 OK`
```json
{
  "bug": 15,
  "feature": 12,
  "tech-debt": 5,
  "documentation": 3
}
```

---

### GET /api/stats/issues/creators

Per-creator issue quality analytics. Returns metrics for every user who created issues in the date range, plus team-wide averages for comparison. Helps management identify creators whose task definitions cause friction. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Start of date range (ISO 8601) |
| `date_to` | datetime | now | End of date range (ISO 8601) |
| `team` | string | - | Filter by team (creator must be a registered developer on that team) |

**Note:** Filters by `Issue.created_at`. Team filter joins `creator_github_username` to `Developer.github_username` to resolve team membership. External users (not in the developer registry) appear with `null` for `display_name`, `team`, and `role`.

**Response:** `200 OK`
```json
{
  "creators": [
    {
      "github_username": "alice",
      "display_name": "Alice Smith",
      "team": "platform",
      "role": "tech_lead",
      "issues_created": 28,
      "avg_time_to_close_hours": 72.3,
      "avg_comment_count_before_pr": 3.2,
      "pct_with_checklist": 64.3,
      "pct_reopened": 7.1,
      "pct_closed_not_planned": 3.6,
      "avg_prs_per_issue": 1.2,
      "issues_with_body_under_100_chars": 2,
      "avg_time_to_first_pr_hours": 18.5
    },
    {
      "github_username": "bob",
      "display_name": "Bob Jones",
      "team": "backend",
      "role": "developer",
      "issues_created": 5,
      "avg_time_to_close_hours": 120.0,
      "avg_comment_count_before_pr": null,
      "pct_with_checklist": 20.0,
      "pct_reopened": 40.0,
      "pct_closed_not_planned": 20.0,
      "avg_prs_per_issue": null,
      "issues_with_body_under_100_chars": 3,
      "avg_time_to_first_pr_hours": null
    }
  ],
  "team_averages": {
    "github_username": "__team_average__",
    "display_name": null,
    "team": null,
    "role": null,
    "issues_created": 17,
    "avg_time_to_close_hours": 96.2,
    "avg_comment_count_before_pr": 3.2,
    "pct_with_checklist": 42.2,
    "pct_reopened": 23.6,
    "pct_closed_not_planned": 11.8,
    "avg_prs_per_issue": 1.2,
    "issues_with_body_under_100_chars": 3,
    "avg_time_to_first_pr_hours": 18.5
  }
}
```

| Field | Description |
|-------|-------------|
| `creators` | List of per-creator stats, sorted by `issues_created` descending |
| `team_averages` | Aggregated averages across all creators (for comparison/highlighting) |
| `github_username` | GitHub login of the issue creator |
| `display_name` | Developer display name (`null` for external users) |
| `team` | Developer team (`null` for external users) |
| `role` | Developer role (`null` for external users) |
| `issues_created` | Total issues created by this user in the date range |
| `avg_time_to_close_hours` | Average hours from issue creation to close (`null` if none closed) |
| `avg_comment_count_before_pr` | Average issue comments posted before the first linked PR was opened (`null` if no linked PRs). Requires issue-PR linkage via closing keywords. |
| `pct_with_checklist` | Percentage of issues containing `- [ ]` or `- [x]` checklist syntax |
| `pct_reopened` | Percentage of issues with `reopen_count > 0` |
| `pct_closed_not_planned` | Percentage of closed issues with `state_reason == "not_planned"` |
| `avg_prs_per_issue` | Average PRs linked per issue via closing keywords (`null` if no linked PRs). Values >1 suggest scope too large. |
| `issues_with_body_under_100_chars` | Count of issues with body < 100 characters (poorly described) |
| `avg_time_to_first_pr_hours` | Average hours from issue creation to first linked PR (`null` if no linked PRs). Long waits suggest unclear requirements. |

---

### GET /api/stats/pr/{pr_id}/risk

Risk assessment for a single PR. Computes a risk score (0.0-1.0) based on 10 weighted factors. **Admin only.**

| Path Param | Type | Description |
|------------|------|-------------|
| `pr_id` | int | Internal DB ID of the pull request |

**Response:** `200 OK`
```json
{
  "pr_id": 42,
  "number": 123,
  "title": "Rewrite auth middleware",
  "html_url": "https://github.com/org/repo/pull/123",
  "repo_name": "org/repo",
  "author_name": "Alice",
  "author_id": 1,
  "risk_score": 0.65,
  "risk_level": "high",
  "risk_factors": [
    {
      "factor": "large_pr",
      "weight": 0.20,
      "description": "Large PR with 700 additions"
    },
    {
      "factor": "many_files",
      "weight": 0.10,
      "description": "Touches 22 files"
    },
    {
      "factor": "fast_tracked",
      "weight": 0.15,
      "description": "Merged in 1.5h (under 2h threshold)"
    },
    {
      "factor": "self_merged",
      "weight": 0.10,
      "description": "PR was merged by its own author"
    },
    {
      "factor": "hotfix_branch",
      "weight": 0.10,
      "description": "Branch 'hotfix/auth-fix' indicates a hotfix"
    }
  ],
  "is_open": false
}
```

**Error:** `404 Not Found` if `pr_id` does not exist.

**Risk factors (10 total):**

| Factor | Condition | Weight |
|--------|-----------|--------|
| `large_pr` | additions > 500 | +0.20 |
| `very_large_pr` | additions > 1000 (replaces `large_pr`) | +0.35 |
| `many_files` | changed_files > 15 | +0.10 |
| `new_contributor` | author has < 5 merged PRs in this repo, or not in team registry | +0.15 |
| `no_review` | merged with no APPROVED review | +0.25 |
| `rubber_stamp_only` | all reviews have `quality_tier = "rubber_stamp"` | +0.20 |
| `fast_tracked` | merged with `time_to_merge_s < 7200` (2 hours) | +0.15 |
| `self_merged` | `is_self_merged = true` | +0.10 |
| `high_review_rounds` | `review_round_count >= 3` | +0.10 |
| `hotfix_branch` | `head_branch` starts with `hotfix/` or `fix/` | +0.10 |

**Score:** `min(1.0, sum of applicable factor weights)`

**Risk levels:** `low` (0-0.3), `medium` (0.3-0.6), `high` (0.6-0.8), `critical` (0.8-1.0)

---

### GET /api/stats/risk-summary

Team-level risk summary for PRs in the given period. Returns PRs at or above the specified risk level. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter by team (PRs authored by team members) |
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |
| `min_risk_level` | `low` \| `medium` \| `high` \| `critical` | `medium` | Only include PRs at or above this risk level |
| `scope` | `all` \| `open` \| `merged` | `all` | Filter by PR state |

Draft PRs are excluded from scoring.

**Response:** `200 OK`
```json
{
  "high_risk_prs": [
    {
      "pr_id": 42,
      "number": 123,
      "title": "Rewrite auth middleware",
      "html_url": "https://github.com/org/repo/pull/123",
      "repo_name": "org/repo",
      "author_name": "Alice",
      "author_id": 1,
      "risk_score": 0.65,
      "risk_level": "high",
      "risk_factors": [
        {
          "factor": "large_pr",
          "weight": 0.20,
          "description": "Large PR with 700 additions"
        },
        {
          "factor": "fast_tracked",
          "weight": 0.15,
          "description": "Merged in 1.5h (under 2h threshold)"
        },
        {
          "factor": "self_merged",
          "weight": 0.10,
          "description": "PR was merged by its own author"
        },
        {
          "factor": "new_contributor",
          "weight": 0.15,
          "description": "Author has only 3 merged PR(s) in this repo"
        }
      ],
      "is_open": false
    }
  ],
  "total_scored": 47,
  "avg_risk_score": 0.18,
  "prs_by_level": {
    "low": 32,
    "medium": 10,
    "high": 4,
    "critical": 1
  }
}
```

| Field | Description |
|-------|-------------|
| `high_risk_prs` | PRs at or above `min_risk_level`, sorted by risk score descending |
| `total_scored` | Total number of PRs scored in the period (all levels) |
| `avg_risk_score` | Mean risk score across all scored PRs (0.0-1.0) |
| `prs_by_level` | Count of PRs in each risk level bucket |

Invalid `min_risk_level` or `scope` values return `422 Unprocessable Entity`.

---

### GET /api/stats/ci

CI/CD check-run analysis across all repos or scoped to a single repo. **Admin only.**

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `date_from` | datetime (ISO 8601) | 30 days ago | Start of date range |
| `date_to` | datetime (ISO 8601) | now | End of date range |
| `repo_id` | integer | _(none)_ | Optional — scope results to a single repository |

**Response `200 OK`:**

```json
{
  "prs_merged_with_failing_checks": 3,
  "avg_checks_to_green": 1.4,
  "flaky_checks": [
    {
      "name": "integration-tests",
      "failure_rate": 0.182,
      "total_runs": 22
    }
  ],
  "avg_build_duration_s": 245.3,
  "slowest_checks": [
    {
      "name": "e2e-tests",
      "avg_duration_s": 612.5
    },
    {
      "name": "integration-tests",
      "avg_duration_s": 340.2
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `prs_merged_with_failing_checks` | Count of merged PRs that had at least one check run with `conclusion="failure"` |
| `avg_checks_to_green` | Average number of `run_attempt` values before a check passed. `null` if no successful checks exist |
| `flaky_checks` | Check names with >10% failure rate (minimum 5 runs). Sorted by failure rate descending |
| `avg_build_duration_s` | Mean duration in seconds across all check runs with timing data. `null` if no duration data |
| `slowest_checks` | Top 5 check names ranked by average duration, descending |

---

### GET /api/stats/dora

All four DORA metrics: deployment frequency, change lead time, change failure rate (CFR), and mean time to recovery (MTTR) from GitHub Actions workflow runs. Only returns data when `DEPLOY_WORKFLOW_NAME` is configured. **Admin only.**

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `date_from` | datetime (ISO 8601) | 30 days ago | Start of date range |
| `date_to` | datetime (ISO 8601) | now | End of date range |
| `repo_id` | integer | _(none)_ | Optional — scope results to a single repository |

**Response `200 OK`:**

```json
{
  "deploy_frequency": 0.429,
  "deploy_frequency_band": "medium",
  "avg_lead_time_hours": 18.5,
  "lead_time_band": "high",
  "total_deployments": 13,
  "total_all_deployments": 15,
  "period_days": 30,
  "change_failure_rate": 13.33,
  "cfr_band": "high",
  "avg_mttr_hours": 4.5,
  "mttr_band": "high",
  "failure_deployments": 2,
  "overall_band": "medium",
  "deployments": [
    {
      "id": 42,
      "repo_name": "org/api-service",
      "environment": "production",
      "sha": "abc123def456789...",
      "deployed_at": "2026-03-27T14:30:00Z",
      "workflow_name": "deploy-production",
      "status": "success",
      "lead_time_hours": 4.25,
      "is_failure": false,
      "failure_detected_via": null,
      "recovery_time_hours": null
    },
    {
      "id": 41,
      "repo_name": "org/api-service",
      "environment": "production",
      "sha": "def456789abc123...",
      "deployed_at": "2026-03-26T10:00:00Z",
      "workflow_name": "deploy-production",
      "status": "success",
      "lead_time_hours": 2.0,
      "is_failure": true,
      "failure_detected_via": "revert_pr",
      "recovery_time_hours": 4.5
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `deploy_frequency` | Successful deployments per day in the period (`total_deployments / period_days`) |
| `deploy_frequency_band` | DORA benchmark: `elite` (>1/day), `high` (daily–weekly), `medium` (weekly–monthly), `low` (<monthly) |
| `avg_lead_time_hours` | Average hours from oldest undeployed merged PR to deployment. `null` if no lead time data |
| `lead_time_band` | DORA benchmark: `elite` (<1h), `high` (<1 day), `medium` (<1 week), `low` (>1 week) |
| `total_deployments` | Count of successful deployments in the period |
| `total_all_deployments` | Count of all deployments (success + failure) — CFR denominator |
| `period_days` | Number of days in the queried date range |
| `change_failure_rate` | Percentage of deployments that caused a failure. `null` if no deployments |
| `cfr_band` | DORA research benchmark: `elite` (<5%), `high` (<15%), `medium` (<45%), `low` (>=45%) |
| `avg_mttr_hours` | Mean time to recovery in hours. `null` if no failures with recovery data |
| `mttr_band` | DORA benchmark: `elite` (<1h), `high` (<24h), `medium` (<168h), `low` (>=168h) |
| `failure_deployments` | Count of deployments flagged as failures in the period |
| `overall_band` | Overall DORA performance level — lowest (worst) of all 4 metric bands |
| `deployments` | Last 20 deployments (all statuses) in the period, ordered by `deployed_at` descending |

**Deployment detail fields:**

| Field | Description |
|-------|-------------|
| `id` | Deployment record ID |
| `repo_name` | Repository full name (e.g. `org/repo`) |
| `environment` | Deployment environment (from `DEPLOY_ENVIRONMENT` config, default `"production"`) |
| `sha` | Deployed commit SHA |
| `deployed_at` | Deployment completion timestamp (ISO 8601) |
| `workflow_name` | GitHub Actions workflow name |
| `status` | Workflow run conclusion (`"success"`, `"failure"`, etc.) |
| `lead_time_hours` | Hours from oldest undeployed merged PR to this deployment. `null` for the first deployment (no prior reference) |
| `is_failure` | Whether this deployment was flagged as a failure |
| `failure_detected_via` | How the failure was detected: `"failed_deploy"`, `"revert_pr"`, or `"hotfix_pr"`. `null` if not a failure |
| `recovery_time_hours` | Hours from this failure to the next successful non-failure deployment. `null` if not a failure or no recovery yet |

**Failure detection signals:**
1. **Failed workflow runs** — `conclusion != "success"` on the GitHub Actions run
2. **Revert PRs** — a PR with `is_revert=true` merged within 48h after the deployment
3. **Hotfix PRs** — a PR matching configured labels (`HOTFIX_LABELS`) or branch prefixes (`HOTFIX_BRANCH_PREFIXES`) merged within 48h

**Configuration:** Deployment sync requires `DEPLOY_WORKFLOW_NAME` to be set to the exact name of the GitHub Actions workflow that represents a production deployment. If empty, no deployments are synced and this endpoint returns zero values. Failure detection is configurable via `HOTFIX_LABELS` (comma-separated, default `hotfix,urgent,incident`) and `HOTFIX_BRANCH_PREFIXES` (comma-separated, default `hotfix/`).

---

## Work Allocation

Classifies merged PRs and created issues into work categories: `feature`, `bugfix`, `tech_debt`, `ops`, `unknown`. Classification uses a 3-tier pipeline: GitHub labels → title keyword regex → optional AI (Claude API). Manual overrides are authoritative and never re-classified.

### GET /api/stats/work-allocation

**Access:** Admin only

Get aggregate work allocation breakdown for the selected period.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `team` | string | No | Filter by team name |
| `date_from` | datetime | No | Start of period (default: 30 days ago) |
| `date_to` | datetime | No | End of period (default: now) |
| `use_ai` | bool | No | Enable AI classification for unknown items (default: false) |

**Response:** `200 OK`
```json
{
  "period_start": "2026-03-01T00:00:00Z",
  "period_end": "2026-03-30T00:00:00Z",
  "period_type": "weekly",
  "pr_allocation": [
    { "category": "feature", "count": 15, "additions": 2400, "deletions": 300, "pct_of_total": 50.0 },
    { "category": "bugfix", "count": 8, "additions": 500, "deletions": 200, "pct_of_total": 26.7 }
  ],
  "issue_allocation": [
    { "category": "bugfix", "count": 12, "pct_of_total": 40.0 }
  ],
  "developer_breakdown": [
    {
      "developer_id": 1,
      "github_username": "dev1",
      "display_name": "Developer One",
      "team": "platform",
      "pr_categories": { "feature": 5, "bugfix": 3 },
      "issue_categories": { "bugfix": 2 },
      "total_prs": 8,
      "total_issues": 2
    }
  ],
  "trend": [
    {
      "period_start": "2026-03-01T00:00:00Z",
      "period_end": "2026-03-07T00:00:00Z",
      "period_label": "Mar 1",
      "pr_categories": { "feature": 4, "bugfix": 2 },
      "issue_categories": { "bugfix": 3 }
    }
  ],
  "unknown_pct": 10.0,
  "ai_classified_count": 0,
  "total_prs": 30,
  "total_issues": 30
}
```

### GET /api/stats/work-allocation/items

**Access:** Any authenticated user

Get paginated list of PRs/issues for a specific work category. Used for drill-down from the Investment charts.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | Yes | One of: `feature`, `bugfix`, `tech_debt`, `ops`, `unknown` |
| `type` | string | No | Filter by item type: `all` (default), `pr`, `issue` |
| `date_from` | datetime | No | Start of period (default: 30 days ago) |
| `date_to` | datetime | No | End of period (default: now) |
| `page` | int | No | Page number (default: 1, min: 1) |
| `page_size` | int | No | Items per page (default: 20, min: 1, max: 100) |

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": 123,
      "type": "pr",
      "number": 45,
      "title": "Add dashboard widget",
      "labels": ["feature"],
      "repo_name": "backend",
      "author_name": "Developer One",
      "author_id": 1,
      "html_url": "https://github.com/org/backend/pull/45",
      "category": "feature",
      "category_source": "label",
      "merged_at": "2026-03-15T10:30:00Z",
      "created_at": null,
      "additions": 200,
      "deletions": 50
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 20
}
```

| Field | Description |
|-------|-------------|
| `type` | `"pr"` or `"issue"` |
| `category_source` | How the category was determined: `"label"` (GitHub label match), `"title"` (title keyword match), `"ai"` (Claude classification), `"manual"` (user override), `"cross_ref"` (inherited from linked issue), or `"unknown"` (no match) |
| `merged_at` | Set for PRs, `null` for issues |
| `created_at` | Set for issues, `null` for PRs |
| `additions`/`deletions` | Set for PRs, `null` for issues |

### PATCH /api/stats/work-allocation/items/{item_type}/{item_id}/category

**Access:** Any authenticated user

Recategorize a PR or issue. Sets `work_category_source` to `"manual"`, which is authoritative and never overwritten by re-sync or AI reclassification.

| Path Parameter | Type | Description |
|----------------|------|-------------|
| `item_type` | string | `"pr"` or `"issue"` |
| `item_id` | int | Database ID of the item |

**Request body:**
```json
{
  "category": "bugfix"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `category` | string | Yes | Must be one of: `feature`, `bugfix`, `tech_debt`, `ops`. Cannot be `unknown`. |

**Response:** `200 OK` — returns the updated `WorkAllocationItem` (same schema as items in the list endpoint).

**Error responses:**
- `400` — invalid `item_type` (not `pr`/`issue`), invalid category, or item not found
- `422` — category is `unknown` or not in valid set

---

## Work Categories

**Access:** Read endpoints are available to any authenticated user. All mutation endpoints require admin role.

### GET /api/work-categories

List all work category definitions, ordered by `display_order`.

**Response:** `200 OK`
```json
[
  {
    "category_key": "feature",
    "display_name": "Feature",
    "description": "New functionality or enhancements that add user-facing value.",
    "color": "#3b82f6",
    "exclude_from_stats": false,
    "display_order": 1,
    "is_default": true
  }
]
```

### POST /api/work-categories

Create a new work category. **Admin only.**

**Request body:**
```json
{
  "category_key": "security",
  "display_name": "Security",
  "description": "Security-related fixes and hardening work.",
  "color": "#dc2626",
  "exclude_from_stats": false
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `category_key` | string | Yes | Lowercase alphanumeric + underscores, 2-49 chars, starts with letter |
| `display_name` | string | Yes | |
| `description` | string | No | |
| `color` | string | Yes | Hex color like `#3b82f6` |
| `exclude_from_stats` | bool | No | Default `false` |

**Response:** `201 Created` — returns the created `WorkCategoryResponse`.

**Error responses:**
- `409` — duplicate key, invalid key format, or invalid color

### PATCH /api/work-categories/{category_key}

Update a work category. **Admin only.**

**Request body:** Any subset of `display_name`, `description`, `color`, `exclude_from_stats`, `display_order`.

**Response:** `200 OK` — returns the updated category.

**Error responses:**
- `404` — category not found
- `409` — cannot exclude `unknown` from stats, invalid color

### DELETE /api/work-categories/{category_key}

Delete a work category. **Admin only.** Cannot delete default categories or categories with assigned items.

**Response:** `204 No Content`

**Error responses:**
- `404` — category not found
- `409` — default category or has assigned PRs/issues

### GET /api/work-categories/rules

List all classification rules, ordered by `priority` ascending.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "match_type": "label",
    "match_value": "bug",
    "description": null,
    "case_sensitive": false,
    "category_key": "bugfix",
    "priority": 10
  }
]
```

### POST /api/work-categories/rules

Create a classification rule. **Admin only.**

**Request body:**
```json
{
  "match_type": "label",
  "match_value": "epic",
  "description": "Maps GitHub 'epic' label to feature category.",
  "case_sensitive": false,
  "category_key": "feature",
  "priority": 50
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `match_type` | string | Yes | One of: `label`, `issue_type`, `title_regex`, `prefix` |
| `match_value` | string | Yes | For `title_regex`: must be valid regex |
| `description` | string | No | |
| `case_sensitive` | bool | No | Default `false` |
| `category_key` | string | Yes | Must reference existing category |
| `priority` | int | Yes | Lower = evaluated first |

**Response:** `201 Created` — returns the created rule.

**Error responses:**
- `409` — invalid match_type, invalid regex, or nonexistent category

### PATCH /api/work-categories/rules/{rule_id}

Update a classification rule. **Admin only.**

**Request body:** Any subset of rule fields.

**Response:** `200 OK` — returns the updated rule.

### DELETE /api/work-categories/rules/{rule_id}

Delete a classification rule. **Admin only.**

**Response:** `204 No Content`

### POST /api/work-categories/rules/bulk

Create multiple classification rules in one transaction. **Admin only.** Used by the suggestions approve flow.

**Request body:**
```json
{
  "rules": [
    {
      "match_type": "label",
      "match_value": "priority-high",
      "category_key": "feature",
      "priority": 45,
      "case_sensitive": false,
      "description": null
    },
    {
      "match_type": "issue_type",
      "match_value": "Epic",
      "category_key": "feature",
      "priority": 55,
      "case_sensitive": false,
      "description": null
    }
  ]
}
```

**Response:** `201 Created`
```json
{
  "created": 2
}
```

**Error responses:**
- `409` — any rule has invalid match_type, invalid regex, or nonexistent category (entire batch rejected)

### POST /api/work-categories/suggestions

Scan synced GitHub data for labels and issue types not covered by any existing rule. Returns suggestions sorted by usage count descending. **Admin only.**

**Request body:** None

**Response:** `200 OK`
```json
[
  {
    "match_type": "label",
    "match_value": "priority-high",
    "suggested_category": "unknown",
    "usage_count": 47
  },
  {
    "match_type": "issue_type",
    "match_value": "Epic",
    "suggested_category": "unknown",
    "usage_count": 12
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `match_type` | string | `"label"` or `"issue_type"` |
| `match_value` | string | The label name or issue type string from GitHub |
| `suggested_category` | string | Best-guess category key based on keyword matching. Falls back to `"unknown"`. |
| `usage_count` | int | Number of PRs + issues using this label/type |

Category suggestions use keyword substring matching: labels containing "bug"/"defect"/"hotfix" → `bugfix`, "feature"/"enhancement" → `feature`, "refactor"/"chore"/"deps" → `tech_debt`, "infra"/"deploy"/"docs" → `ops`, etc.

### POST /api/work-categories/reclassify

Reclassify all non-manual PRs and issues using current rules. **Admin only.**

**Request body:** None

**Response:** `200 OK`
```json
{
  "prs_updated": 142,
  "issues_updated": 87,
  "duration_s": 1.23
}
```

---

## Developer Goals

**Access:** Admin has full CRUD. Developers can view their own goals, create self-goals via `/goals/self`, and update their own self-created goals.

### POST /api/goals

Create a goal for a developer. Baseline value is auto-computed from the current 30-day window. **Admin only.**

**Request Body:**
```json
{
  "developer_id": 1,
  "title": "Reduce avg PR size",
  "description": "Target smaller, more focused PRs",
  "metric_key": "avg_pr_additions",
  "target_value": 200,
  "target_direction": "below",
  "target_date": "2026-06-01"
}
```

`metric_key` values: `avg_pr_additions`, `time_to_merge_h`, `reviews_given`, `review_quality_score`, `prs_merged`, `time_to_first_review_h`, `issues_closed`, `prs_opened`

`target_direction`: `"above"` (metric should be >= target) or `"below"` (metric should be <= target)

**Response:** `200 OK` — `GoalResponse`

### GET /api/goals?developer_id={id}

List all goals for a developer, ordered by creation date (newest first). **Developers can only list their own goals.**

**Response:** `200 OK` — `GoalResponse[]`
**Errors:** `403 Forbidden` (developer accessing another developer's goals)

### PATCH /api/goals/{goal_id}

Update goal status or notes. **Admin only.**

**Request Body:**
```json
{
  "status": "achieved",
  "notes": "Consistently under 200 additions since Feb"
}
```

`status` values: `active`, `achieved`, `abandoned`

**Response:** `200 OK` — `GoalResponse`

### POST /api/goals/self

Create a goal for the authenticated developer. `developer_id` is derived from the JWT token. Baseline value is auto-computed from the current 30-day window. The goal is marked `created_by: "self"`. **Any authenticated user.**

**Request Body:**
```json
{
  "title": "Ship more PRs",
  "description": "Focus on smaller, frequent merges",
  "metric_key": "prs_merged",
  "target_value": 12,
  "target_direction": "above",
  "target_date": "2026-06-01"
}
```

Only `title`, `metric_key`, and `target_value` are required. No `developer_id` field — it is set from the token.

**Response:** `200 OK` — `GoalResponse` (with `created_by: "self"`)

### PATCH /api/goals/self/{goal_id}

Update a self-created goal. Developers can only update goals they created themselves (`created_by: "self"`). Admin-created goals return `403`. **Any authenticated user (own goals only).**

**Request Body:**
```json
{
  "target_value": 15,
  "target_date": "2026-07-01",
  "status": "achieved",
  "notes": "Consistently hitting target"
}
```

All fields are optional. `status` values: `active`, `achieved`, `abandoned`.

**Response:** `200 OK` — `GoalResponse`
**Errors:** `403 Forbidden` (goal belongs to another developer, or goal was admin-created), `404 Not Found`

### GET /api/goals/{goal_id}/progress

Get goal progress with 8-week history. Triggers auto-achievement check: if the metric crosses the target for 2 consecutive weekly periods, the goal is automatically marked as achieved. **Developers can only view their own goals' progress.**

**Response:** `200 OK`
```json
{
  "goal_id": 1,
  "title": "Reduce avg PR size",
  "target_value": 200,
  "target_direction": "below",
  "baseline_value": 350.0,
  "current_value": 180.5,
  "status": "achieved",
  "history": [
    { "period_end": "2026-02-07T00:00:00Z", "value": 320.0 },
    { "period_end": "2026-02-14T00:00:00Z", "value": 280.0 },
    { "period_end": "2026-03-28T00:00:00Z", "value": 180.5 }
  ]
}
```

---

## Sync

**All sync endpoints are admin only.** Returns `409 Conflict` if a sync is already running (concurrency guard).

### POST /api/sync/start

Start a new sync. Supports full or incremental, optional repo filtering and time range override.

**Request Body:** `SyncTriggerRequest`
```json
{
  "sync_type": "incremental",
  "repo_ids": [1, 2, 3],
  "since": "2026-01-01T00:00:00Z",
  "sync_scope": "3 repos · 30 days"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sync_type` | `"full"` \| `"incremental"` | `"incremental"` | Full re-syncs all data; incremental fetches since each repo's `last_synced_at`. Note: `"contributors"` is also a valid sync_type (created by `POST /sync/contributors`), but not accepted here. |
| `repo_ids` | `int[]` \| `null` | `null` | Specific repo IDs to sync. `null` = all tracked repos |
| `since` | `datetime` \| `null` | `null` | Override per-repo `last_synced_at` with a uniform date |
| `sync_scope` | `string` \| `null` | `null` | Human-readable description of what is being synced (e.g., "3 repos · 30 days"). Stored on the SyncEvent for display in history. |

**Response:** `202 Accepted`
```json
{ "status": "accepted", "sync_type": "incremental" }
```

**Error:** `409 Conflict` — a sync is already in progress.

### POST /api/sync/resume/{event_id}

Resume an interrupted sync, processing only repos that were not completed in the original run.

**Path Params:** `event_id` (int) — ID of the failed/partial/cancelled sync event to resume.

**Response:** `202 Accepted`
```json
{ "status": "accepted", "remaining_repos": 5 }
```

**Errors:**
- `404` — sync event not found
- `400` — event is not resumable or no remaining repos
- `409` — a sync is already in progress

### POST /api/sync/cancel

Request graceful cancellation of the active sync. Sets `cancel_requested = true` on the running SyncEvent. The sync loop checks this flag at repo boundaries and every 50-PR batch, then exits cleanly with `status = "cancelled"` and `is_resumable = true`.

**Response:** `200 OK`
```json
{ "status": "cancel_requested", "event_id": 42 }
```

**Errors:** `404` — no active sync to cancel.

### POST /api/sync/contributors

Sync GitHub org members and backfill author/reviewer/assignee links on existing PRs, reviews, and issues. Runs as a background task. Does NOT trigger a full data sync — only discovers contributors and links them to existing records.

Creates a `SyncEvent` with `sync_type = "contributors"` for progress tracking. The event is visible via `GET /api/sync/status` (as `active_sync` while running) and in sync history. Uses `repos_synced` to report the number of newly created developers.

Two-step process:
1. Fetches all members from `GET /orgs/{org}/members` and creates `developers` rows for any that don't exist yet (with `app_role = "developer"`, `is_active = true`, `display_name = login`). If a previously deactivated developer is found in the org member list, they are auto-reactivated with a warning log entry.
2. Bulk-updates `pull_requests.author_id`, `pr_reviews.reviewer_id`, and `issues.assignee_id` where the FK is NULL but the stored `*_github_username` column matches a known developer.

**Response:** `202 Accepted`
```json
{ "status": "accepted" }
```

**Errors:**
- `409` — a sync is already in progress

---

### POST /api/sync/force-stop

Force-stop a stale or stuck sync by directly marking it as `cancelled` + `is_resumable = true`. Use when the background task has crashed and the sync is stuck in `started` status.

**Response:** `200 OK`
```json
{ "status": "force_stopped", "event_id": 42 }
```

**Errors:** `404` — no active sync to stop.

### GET /api/sync/status

Get the current sync state: active sync (if any), last completed sync, and summary stats.

**Response:** `200 OK` — `SyncStatusResponse`
```json
{
  "active_sync": {
    "id": 42,
    "sync_type": "incremental",
    "status": "started",
    "total_repos": 50,
    "current_repo_name": "org/repo-name",
    "current_step": "processing_prs",
    "current_repo_prs_total": 200,
    "current_repo_prs_done": 42,
    "current_repo_issues_total": null,
    "current_repo_issues_done": null,
    "repos_completed": [
      { "repo_id": 1, "repo_name": "org/repo-a", "status": "ok", "prs": 15, "issues": 3, "warnings": [] }
    ],
    "repos_failed": [],
    "repos_synced": 23,
    "prs_upserted": 150,
    "issues_upserted": 45,
    "errors": [],
    "log_summary": [
      { "ts": "10:32:15", "level": "info", "msg": "Starting sync", "repo": "org/repo-a" }
    ],
    "rate_limit_wait_s": 0,
    "cancel_requested": false,
    "is_resumable": false,
    "resumed_from_id": null,
    "triggered_by": "scheduled",
    "sync_scope": "All tracked repos · incremental",
    "started_at": "2026-03-28T10:30:00Z",
    "completed_at": null,
    "duration_s": null
  },
  "last_completed": null,
  "tracked_repos_count": 42,
  "total_repos_count": 50,
  "last_successful_sync": "2026-03-27T10:30:00Z",
  "last_sync_duration_s": 1234,
  "schedule": {
    "auto_sync_enabled": true,
    "incremental_interval_minutes": 15,
    "full_sync_cron_hour": 2,
    "updated_at": "2026-03-28T10:00:00Z"
  }
}
```

### GET /api/sync/schedule

Get the sync schedule configuration (auto-sync toggle, intervals).

**Response:** `200 OK` — `SyncScheduleConfigResponse`
```json
{
  "auto_sync_enabled": true,
  "incremental_interval_minutes": 15,
  "full_sync_cron_hour": 2,
  "linear_sync_enabled": true,
  "linear_sync_interval_minutes": 120,
  "updated_at": "2026-03-28T10:00:00Z"
}
```

Returns defaults (`true`, `15`, `2`, `true`, `120`) if no config row exists yet.

### PATCH /api/sync/schedule

Update the sync schedule configuration. Changes take effect immediately — APScheduler jobs are rescheduled live.

**Request Body:** `SyncScheduleConfigUpdate` — all fields optional
```json
{
  "auto_sync_enabled": false,
  "incremental_interval_minutes": 30,
  "full_sync_cron_hour": 4,
  "linear_sync_enabled": true,
  "linear_sync_interval_minutes": 60
}
```

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `auto_sync_enabled` | `bool` | | Enable/disable automatic GitHub background syncing |
| `incremental_interval_minutes` | `int` | >= 5 | Minutes between incremental GitHub syncs |
| `full_sync_cron_hour` | `int` | 0-23 | Hour (server time) for nightly full GitHub sync |
| `linear_sync_enabled` | `bool` | | Enable/disable automatic Linear background syncing |
| `linear_sync_interval_minutes` | `int` | >= 5 | Minutes between Linear syncs (default 120) |

**Response:** `200 OK` — `SyncScheduleConfigResponse` (updated values)

**Errors:**
- `400` — interval < 5 or hour outside 0-23

---

### POST /api/sync/discover-repos

Fetch repos from the GitHub org and upsert them into the database. Does NOT run a full sync — only discovers repos so users can select which ones to track/sync.

**Response:** `200 OK` — `RepoResponse[]` (same format as `GET /api/sync/repos`)

### GET /api/sync/repos

List all repositories with PR and issue counts.

**Response:** `200 OK` — `RepoResponse[]`
```json
[
  {
    "id": 1,
    "github_id": 123456,
    "name": "repo-name",
    "full_name": "org/repo-name",
    "description": "Description",
    "language": "Python",
    "is_tracked": true,
    "last_synced_at": "2026-03-28T10:30:00Z",
    "created_at": "2026-01-01T00:00:00Z",
    "pr_count": 150,
    "issue_count": 45
  }
]
```

### PATCH /api/sync/repos/{repo_id}/track

Enable or disable tracking for a repository.

**Request Body:**
```json
{ "is_tracked": true }
```

**Response:** `200 OK` — `RepoResponse` (includes `pr_count`, `issue_count`)

### DELETE /api/sync/repos/{repo_id}/data

Purge all synced data for a single repo — PRs, reviews, review comments, files, check runs, external-issue links, issues, issue comments, deployments, and tree files. The `repositories` row itself is kept but `is_tracked` is set to `false` and `last_synced_at` is cleared so future syncs skip it unless re-enabled. Other repos are untouched. Aggregates like `developer_collaboration_scores` and `sync_events` history are not cleaned — collaboration scores recompute on next sync; sync events are historical records.

Useful for removing data from repos the GitHub App has access to but the user doesn't want tracked (e.g. filtering work repos out of a personal dashboard).

**Response:** `200 OK` — `RepoDataDeleteResponse`
```json
{
  "repo_id": 42,
  "full_name": "org/repo",
  "deleted": {
    "pull_requests": 150,
    "pr_reviews": 320,
    "pr_review_comments": 84,
    "pr_files": 1240,
    "pr_check_runs": 890,
    "pr_external_issue_links": 0,
    "issues": 45,
    "issue_comments": 120,
    "deployments": 200,
    "repo_tree_files": 0
  }
}
```

**Errors:** `404` — repository not found.

### GET /api/sync/events/{event_id}

Get a single sync event by ID with full progress, error, and log details.

**Path Params:** `event_id` (int)

**Response:** `200 OK` — `SyncEventResponse`

**Errors:** `404` — sync event not found.

### GET /api/sync/events

List recent sync events with full progress and error details.

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `limit` | int (1-200) | `50` | Max events to return |

**Response:** `200 OK` — `SyncEventResponse[]` ordered by `started_at` desc

Each event includes:
- `repo_ids`, `since_override` — sync scope configuration
- `total_repos`, `repos_synced` — progress counters
- `current_repo_name` — currently syncing repo (null when idle/done)
- `current_step` — active phase within repo: `fetching_prs`, `processing_prs`, `fetching_issues`, `processing_issues`, `processing_issue_comments`, `syncing_file_tree`, `fetching_deployments` (null when idle/done)
- `current_repo_prs_total`, `current_repo_prs_done` — PR-level progress within current repo
- `current_repo_issues_total`, `current_repo_issues_done` — issue-level progress within current repo
- `repos_completed` — list of `{repo_id, repo_name, status, prs, issues, warnings}`
- `repos_failed` — list of `{repo_id, repo_name, error}`
- `errors` — structured error objects (see below)
- `log_summary` — sync log entries `{ts, level, msg, repo?}` (max 500, priority eviction)
- `cancel_requested` — `true` if cancellation has been requested
- `is_resumable` — `true` if sync can be resumed via `POST /sync/resume/{id}`
- `resumed_from_id` — links to the original interrupted sync event
- `rate_limit_wait_s` — total seconds spent waiting for GitHub rate limits
- `triggered_by` — origin of the sync: `"manual"`, `"scheduled"`, or `"auto_resume"` (null for old events)
- `sync_scope` — human-readable description (e.g., "3 repos · 30 days", "All tracked repos · nightly full resync") (null for old events)

### Structured Error Objects

Each entry in `SyncEventResponse.errors`:
```json
{
  "repo": "org/repo-name",
  "repo_id": 42,
  "step": "pull_requests",
  "error_type": "github_api",
  "status_code": 502,
  "message": "502 Bad Gateway",
  "retryable": true,
  "timestamp": "2026-03-28T10:32:15Z",
  "attempt": 2
}
```

| `error_type` | `retryable` | Cause |
|-------------|-------------|-------|
| `github_api` (502/503/504) | `true` | Transient GitHub API errors — retried 3x with backoff |
| `timeout` | `true` | Request timeout or connection error |
| `auth` (401/403) | `false` | Token expired or insufficient permissions |
| `github_api` (404/422) | `false` | Resource not found or validation error |
| `unknown` | `false` | Unclassified exception |

### Sync Statuses

| Status | Meaning |
|--------|---------|
| `started` | Sync is currently running |
| `completed` | All repos synced successfully |
| `completed_with_errors` | Some repos succeeded, some failed. `is_resumable = true` |
| `failed` | Top-level failure or all repos failed. `is_resumable = true` |
| `cancelled` | User-cancelled via `POST /sync/cancel` or force-stopped. `is_resumable = true` |

---

## Webhooks

### POST /api/webhooks/github

GitHub webhook receiver. No Bearer auth — uses HMAC signature verification.

**Required Headers:**
- `X-Hub-Signature-256`: HMAC-SHA256 signature of body
- `X-GitHub-Event`: Event type (`pull_request`, `pull_request_review`, `pull_request_review_comment`, `issues`, `issue_comment`)

**Response:** `200 OK` — `{ "status": "ok" }`
**Errors:** `401 Unauthorized` on invalid signature

---

## AI Analysis

**All AI endpoints are admin only.** AI features require `ANTHROPIC_API_KEY` to be set. All analysis calls are synchronous (wait for Claude response). Results are persisted in `ai_analyses` table.

All AI analysis endpoints (`/analyze`, `/one-on-one-prep`, `/team-health`) enforce three guards before calling Claude:
1. **Feature toggle** — returns `403` if the master switch or specific feature is disabled in AI settings
2. **Budget check** — returns `429` if monthly token budget is exceeded
3. **Cooldown dedup** — returns a cached result (with `reused: true`) if an identical analysis was run within the cooldown window. Pass `?force=true` to bypass.

**`AIAnalysisResponse` fields** (returned by all analysis endpoints):

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Analysis row ID |
| `analysis_type` | string | `communication`, `conflict`, `sentiment`, `one_on_one_prep`, `team_health` |
| `scope_type` | string | `developer`, `team`, `repo` |
| `scope_id` | string | Entity ID or name |
| `date_from`, `date_to` | datetime | Analysis period |
| `input_summary` | string | Human-readable summary of data sent to Claude |
| `result` | object | Structured JSON result (schema varies by `analysis_type`) |
| `model_used` | string | Claude model ID (e.g. `claude-sonnet-4-0`) |
| `tokens_used` | int | Total tokens (input + output) |
| `input_tokens` | int or null | Input tokens sent to Claude |
| `output_tokens` | int or null | Output tokens received from Claude |
| `estimated_cost_usd` | float or null | Estimated cost based on configured pricing |
| `reused` | bool | `true` if this result was served from cooldown cache |
| `triggered_by` | string | `"api"` |
| `created_at` | datetime | When the analysis was created |

### POST /api/ai/analyze

Run a standard AI analysis (communication, conflict, or sentiment).

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `force` | bool | `false` | Bypass cooldown cache and always call Claude |

**Request Body:**
```json
{
  "analysis_type": "communication",
  "scope_type": "developer",
  "scope_id": "1",
  "date_from": "2026-02-01T00:00:00Z",
  "date_to": "2026-03-01T00:00:00Z",
  "repo_ids": [1, 2]
}
```

`analysis_type`: `communication`, `conflict`, `sentiment`
`scope_type`: `developer`, `team`, `repo`
`repo_ids`: optional array of repo IDs to filter data (omit for all repos)
`scope_id`: developer ID (string), team name, or repo ID (string)

**Response:** `201 Created` — `AIAnalysisResponse` with structured JSON in `result` field

### POST /api/ai/one-on-one-prep

Generate a structured 1:1 meeting prep brief for a developer.

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `force` | bool | `false` | Bypass cooldown cache and always call Claude |

**Request Body:**
```json
{
  "developer_id": 1,
  "date_from": "2026-02-01T00:00:00Z",
  "date_to": "2026-03-01T00:00:00Z",
  "repo_ids": [1, 2]
}
```

`repo_ids`: optional array — filters PR list and review quality queries to selected repos. Stats/trends/benchmarks remain unfiltered.

**Context gathered:** developer stats, 4-period trends, team benchmarks, PR list, review quality tiers, active goals with progress, previous 1:1 brief (for continuity), issue creator stats with team averages (if developer has created issues in the period), sprint context (if Linear active and developer mapped: active sprint completion/scope, last 3 sprints personal vs team completion, triage stats, estimation patterns by size bucket).

**Response:** `201 Created` — `AIAnalysisResponse` where `result` contains:
```json
{
  "period_summary": "...",
  "metrics_highlights": [
    { "metric": "prs_merged", "value": "10", "context": "Above team median of 7", "concern_level": "none" }
  ],
  "notable_work": ["Led the auth middleware rewrite"],
  "suggested_talking_points": [
    {
      "topic": "Review volume",
      "framing": "I've noticed you've been doing a lot of reviews lately. How are you feeling about the review load?",
      "evidence": "25 reviews given, 2.5x team median"
    }
  ],
  "goal_progress": [
    { "title": "Reduce avg PR size", "status": "active", "current_value": "185" }
  ]
}
```

### POST /api/ai/team-health

Generate a comprehensive team health assessment.

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `force` | bool | `false` | Bypass cooldown cache and always call Claude |

**Request Body:**
```json
{
  "team": "Platform",
  "date_from": "2026-02-01T00:00:00Z",
  "date_to": "2026-03-01T00:00:00Z",
  "repo_ids": [1, 2]
}
```

`team` is optional — omit for all active developers.
`repo_ids`: optional array — filters CR reviews and heated threads to selected repos. Stats/workload/collaboration remain unfiltered.

**Context gathered:** team stats + benchmarks, workload balance + alerts, collaboration matrix + insights, CHANGES_REQUESTED reviews with body text + metadata (up to 60), heated issue threads with full chronological dialogue (3+ comments between 2 tracked devs), active team goals with current values, planning health (if Linear active: velocity trend, completion rate, scope creep, triage health, estimation accuracy, work alignment %, at-risk projects).

**Response:** `201 Created` — `AIAnalysisResponse` where `result` contains:
```json
{
  "overall_health_score": 7,
  "velocity_assessment": "Team is shipping at a sustainable pace...",
  "workload_concerns": [
    { "concern": "Alice is reviewing 2.5x the team median", "suggestion": "Rotate review assignments" }
  ],
  "collaboration_patterns": "Strong intra-team reviews but zero cross-team with Mobile...",
  "communication_flags": [
    { "severity": "medium", "observation": "Recurring terse CHANGES_REQUESTED reviews between Bob and Charlie" }
  ],
  "process_recommendations": ["Implement round-robin review assignment"],
  "strengths": ["Fast time-to-first-review (median 3.8h)", "High merge rate (85%)"],
  "action_items": [
    { "priority": "high", "action": "Address review bottleneck on core-api repo", "owner": "lead" }
  ]
}
```

### GET /api/ai/history

List past analysis results.

| Query Param | Type | Description |
|-------------|------|-------------|
| `analysis_type` | string | Filter: `communication`, `conflict`, `sentiment`, `one_on_one_prep`, `team_health` |
| `scope_type` | string | Filter: `developer`, `team`, `repo` |

**Response:** `200 OK` — `AIAnalysisResponse[]` (last 50, newest first)

### GET /api/ai/history/{analysis_id}

Get a specific analysis result.

**Response:** `200 OK` — `AIAnalysisResponse`

---

## AI Settings & Cost Controls

**All settings endpoints are admin only.** These manage AI feature toggles, budget limits, pricing configuration, and usage tracking.

### GET /api/ai/settings

Get current AI settings and usage summary for the current month.

**Response:** `200 OK`
```json
{
  "ai_enabled": true,
  "feature_general_analysis": true,
  "feature_one_on_one_prep": true,
  "feature_team_health": true,
  "feature_work_categorization": true,
  "monthly_token_budget": 100000,
  "budget_warning_threshold": 0.8,
  "input_token_price_per_million": 3.0,
  "output_token_price_per_million": 15.0,
  "pricing_updated_at": "2026-03-15T10:00:00Z",
  "cooldown_minutes": 30,
  "updated_at": "2026-03-20T14:30:00Z",
  "updated_by": "admin_user",
  "api_key_configured": true,
  "current_month_tokens": 45230,
  "current_month_cost_usd": 1.82,
  "budget_pct_used": 0.4523
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ai_enabled` | bool | Master on/off switch for all AI features |
| `feature_general_analysis` | bool | Toggle for communication/conflict/sentiment analysis |
| `feature_one_on_one_prep` | bool | Toggle for 1:1 prep brief generation |
| `feature_team_health` | bool | Toggle for team health checks |
| `feature_work_categorization` | bool | Toggle for AI batch classification on Investment page |
| `monthly_token_budget` | int or null | Monthly token cap. `null` = unlimited |
| `budget_warning_threshold` | float | Fraction (0-1) at which frontend shows budget warning |
| `input_token_price_per_million` | float | Configurable input token pricing (USD) |
| `output_token_price_per_million` | float | Configurable output token pricing (USD) |
| `pricing_updated_at` | datetime or null | When pricing was last changed. `null` = using defaults |
| `cooldown_minutes` | int | Dedup window — recent analysis results reused within this window |
| `updated_at` | datetime | Last settings change timestamp |
| `updated_by` | string or null | GitHub username of admin who last changed settings |
| `api_key_configured` | bool | `true` if `ANTHROPIC_API_KEY` env var is set |
| `current_month_tokens` | int | Total tokens used this calendar month |
| `current_month_cost_usd` | float | Estimated cost this month based on configured pricing |
| `budget_pct_used` | float or null | `current_month_tokens / monthly_token_budget`. `null` if no budget |

### PATCH /api/ai/settings

Update AI settings. All fields are optional — only provided fields are changed.

**Request Body:**
```json
{
  "ai_enabled": false,
  "feature_work_categorization": false,
  "monthly_token_budget": 200000,
  "cooldown_minutes": 15
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ai_enabled` | bool | Master switch |
| `feature_general_analysis` | bool | Toggle for general analysis |
| `feature_one_on_one_prep` | bool | Toggle for 1:1 prep |
| `feature_team_health` | bool | Toggle for team health |
| `feature_work_categorization` | bool | Toggle for work categorization AI |
| `monthly_token_budget` | int | Set monthly token cap |
| `clear_budget` | bool | Set `true` to remove the budget limit (set to unlimited) |
| `budget_warning_threshold` | float | Warning threshold (0.5-1.0) |
| `input_token_price_per_million` | float | Input pricing — auto-sets `pricing_updated_at` |
| `output_token_price_per_million` | float | Output pricing — auto-sets `pricing_updated_at` |
| `cooldown_minutes` | int | Dedup cooldown window |

**Response:** `200 OK` — Same schema as `GET /api/ai/settings` (returns updated settings with usage)

### GET /api/ai/usage

Usage breakdown by AI feature with daily timeseries.

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `days` | int | `30` | Lookback period (1-365) |

**Response:** `200 OK`
```json
{
  "period_start": "2026-02-26T00:00:00Z",
  "period_end": "2026-03-28T00:00:00Z",
  "total_tokens": 45230,
  "total_cost_usd": 1.82,
  "budget_limit": 100000,
  "budget_pct_used": 0.4523,
  "features": [
    {
      "feature": "general_analysis",
      "enabled": true,
      "label": "General Analysis",
      "description": "AI-powered communication, conflict, and sentiment analysis...",
      "disabled_impact": "Admins cannot run communication, conflict, or sentiment analyses...",
      "tokens_this_month": 12000,
      "cost_this_month_usd": 0.48,
      "call_count_this_month": 3,
      "last_used_at": "2026-03-27T10:00:00Z"
    }
  ],
  "daily_usage": [
    {
      "date": "2026-03-15",
      "tokens": 5000,
      "cost_usd": 0.18,
      "calls": 2,
      "by_feature": {
        "general_analysis": { "tokens": 3000, "calls": 1 },
        "one_on_one_prep": { "tokens": 2000, "calls": 1 }
      }
    }
  ]
}
```

`features` contains one entry per AI feature (general_analysis, one_on_one_prep, team_health, work_categorization) with current month usage and human-readable metadata.

`daily_usage` contains one entry per day with non-zero usage, sorted chronologically.

### POST /api/ai/estimate

Estimate token usage and cost for an AI call without executing it. Does not call Claude. For `one_on_one_prep` and `team_health`, builds the real context (same DB queries as the actual analysis) and measures serialized size for accurate token estimation.

| Query Param | Type | Required | Description |
|-------------|------|----------|-------------|
| `feature` | string | Yes | `general_analysis`, `one_on_one_prep`, `team_health`, `work_categorization` |
| `scope_type` | string | No | `developer`, `team`, `repo` (for general_analysis) |
| `scope_id` | string | No | Entity ID or developer_id or team name |
| `date_from` | datetime | No | Period start (defaults to 30 days ago) |
| `date_to` | datetime | No | Period end (defaults to now) |
| `repo_ids` | string | No | Comma-separated repo IDs for optional filtering (e.g. `1,2,3`) |

**Response:** `200 OK`
```json
{
  "estimated_input_tokens": 12450,
  "estimated_output_tokens": 3000,
  "estimated_cost_usd": 0.0824,
  "data_items": 45,
  "character_count": 34200,
  "system_prompt_tokens": 150,
  "remaining_budget_tokens": 500000,
  "would_exceed_budget": false,
  "note": "Based on actual context (34,200 characters)"
}
```

Estimation methods by feature:
- `general_analysis`: Gathers actual data items, measures serialized JSON size, derives tokens via `chars // 4 + system_prompt_tokens`
- `one_on_one_prep`: Builds the full 1:1 context (stats, trends, benchmarks, PRs, goals), measures serialized size. Requires `scope_id` (developer ID) for accurate estimate; falls back to 5K heuristic without it.
- `team_health`: Builds the full team health context (stats, workload, collaboration, CR reviews, heated threads, goals), measures serialized size
- `work_categorization`: Max batch estimate (200 items)

Budget headroom: `remaining_budget_tokens` is `budget_limit - tokens_used_this_month` (0 if no budget set). `would_exceed_budget` is true if estimated tokens exceed remaining budget.

### AI Analysis Schedules

CRUD for recurring AI analysis schedules. Each schedule is an independent configuration with its own analysis type, scope, repo filter, time range, and cron frequency. APScheduler jobs are registered/updated on create/update/delete.

### GET /api/ai/schedules

List all AI analysis schedules.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "name": "Weekly 1:1 Prep — Alice",
    "analysis_type": "one_on_one_prep",
    "general_type": null,
    "scope_type": "developer",
    "scope_id": "5",
    "repo_ids": null,
    "time_range_days": 30,
    "frequency": "weekly",
    "day_of_week": 0,
    "hour": 8,
    "minute": 0,
    "is_enabled": true,
    "last_run_at": "2026-03-31T08:00:00Z",
    "last_run_analysis_id": 42,
    "last_run_status": "success",
    "created_by": "admin",
    "created_at": "2026-03-15T10:00:00Z",
    "updated_at": "2026-03-15T10:00:00Z",
    "next_run_description": "Weekly on Monday at 8:00 AM"
  }
]
```

### POST /api/ai/schedules

Create a new schedule and register it with APScheduler.

**Request Body:**
```json
{
  "name": "Weekly 1:1 Prep — Alice",
  "analysis_type": "one_on_one_prep",
  "scope_type": "developer",
  "scope_id": "5",
  "repo_ids": [1, 2],
  "time_range_days": 30,
  "frequency": "weekly",
  "day_of_week": 0,
  "hour": 8,
  "minute": 0
}
```

`analysis_type`: `communication`, `conflict`, `sentiment`, `one_on_one_prep`, `team_health`
`frequency`: `daily`, `weekly`, `biweekly`, `monthly`
`day_of_week`: 0=Monday..6=Sunday (required for `weekly` and `biweekly`)
`repo_ids`: optional array of repo IDs to filter analysis data

**Response:** `201 Created` — `AIScheduleResponse`

### PATCH /api/ai/schedules/{schedule_id}

Update a schedule. Only non-null fields are applied. Re-registers the APScheduler job.

**Request Body:** (all fields optional)
```json
{
  "name": "Renamed",
  "is_enabled": false,
  "frequency": "daily",
  "hour": 9
}
```

**Response:** `200 OK` — `AIScheduleResponse`

### DELETE /api/ai/schedules/{schedule_id}

Delete a schedule and remove its APScheduler job.

**Response:** `204 No Content`

### POST /api/ai/schedules/{schedule_id}/run

Manually trigger a scheduled analysis. Computes date range from `time_range_days`, runs the analysis, and updates the schedule's last_run fields.

**Response:** `201 Created` — `AIAnalysisResponse`

---

## Developer Relationships & Org Structure

Manage reporting hierarchies and view organizational structure. Three relationship types: `reports_to`, `tech_lead_of`, `team_lead_of`. A developer can have one of each (e.g., reports to a manager AND has a separate tech lead).

### GET /api/developers/{developer_id}/relationships

Get all relationships for a developer. **Access:** Admin can view any developer. Developers can view their own relationships only.

**Response:** `200 OK`
```json
{
  "reports_to": {
    "id": 1,
    "source_id": 5,
    "target_id": 2,
    "relationship_type": "reports_to",
    "source_name": "Alice",
    "target_name": "Bob",
    "source_avatar_url": "https://...",
    "target_avatar_url": "https://...",
    "created_at": "2026-03-29T10:00:00Z"
  },
  "tech_lead": null,
  "team_lead": null,
  "direct_reports": [],
  "tech_leads_for": [],
  "team_leads_for": []
}
```

`reports_to` / `tech_lead` / `team_lead` are relationships where this developer is the source (they report to / are led by someone). `direct_reports` / `tech_leads_for` / `team_leads_for` are relationships where this developer is the target (others report to / are led by them).

**Errors:** `404 Not Found`, `403 Forbidden`

### POST /api/developers/{developer_id}/relationships

Create a relationship. **Admin only.**

**Request Body:**
```json
{
  "target_id": 2,
  "relationship_type": "reports_to"
}
```

`relationship_type` values: `reports_to`, `tech_lead_of`, `team_lead_of`

**Response:** `200 OK` — `DeveloperRelationshipResponse` (same shape as entries in the GET response)

**Errors:**
- `400 Bad Request` — self-referencing (source_id == target_id)
- `404 Not Found` — source or target developer does not exist

### DELETE /api/developers/{developer_id}/relationships

Remove a relationship. **Admin only.**

**Request Body:**
```json
{
  "target_id": 2,
  "relationship_type": "reports_to"
}
```

**Response:** `204 No Content`

**Errors:** `404 Not Found` — relationship does not exist

### GET /api/org-tree

Build full organizational hierarchy from `reports_to` relationships. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter to developers in a specific team |

**Response:** `200 OK`
```json
{
  "roots": [
    {
      "developer_id": 1,
      "display_name": "CTO",
      "github_username": "cto",
      "avatar_url": "https://...",
      "role": "lead",
      "team": "Engineering",
      "office": "HQ",
      "children": [
        {
          "developer_id": 2,
          "display_name": "Alice",
          "github_username": "alice",
          "avatar_url": null,
          "role": "senior_developer",
          "team": "Platform",
          "office": "Remote",
          "children": []
        }
      ]
    }
  ],
  "unassigned": [
    {
      "developer_id": 5,
      "display_name": "New Dev",
      "github_username": "newdev",
      "avatar_url": null,
      "role": "developer",
      "team": null,
      "office": null,
      "children": []
    }
  ]
}
```

`roots` — developers who have direct reports but do not report to anyone themselves. `unassigned` — developers not in any reporting hierarchy (no parent and no children).

---

## Enhanced Collaboration

Multi-signal collaboration scoring, over-tagged detection, and communication scores. Collaboration scores are materialized after each sync from 5 signals: PR reviews (35%), issue co-comments (20%), co-repo authoring (15%), @mentions (15%), co-assignment (15%).

### GET /api/developers/{developer_id}/works-with

Get top collaborators for a developer, ranked by multi-signal collaboration score. **Access:** Admin can view any developer. Developers can view their own only.

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |
| `limit` | int | 10 | Max collaborators to return (1-50) |

**Response:** `200 OK`
```json
{
  "developer_id": 5,
  "collaborators": [
    {
      "developer_id": 2,
      "display_name": "Alice",
      "github_username": "alice",
      "avatar_url": "https://...",
      "team": "Platform",
      "total_score": 0.72,
      "interaction_count": 34,
      "review_score": 0.85,
      "coauthor_score": 0.60,
      "issue_comment_score": 0.50,
      "mention_score": 0.30,
      "co_assigned_score": 0.40
    }
  ]
}
```

Each signal score is normalized to [0, 1]. `total_score` is the weighted sum (also [0, 1]). `interaction_count` is the raw un-normalized sum across all signals.

### GET /api/stats/over-tagged

Detect developers who appear on an unusually high percentage of PRs and issues relative to their team. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter to a specific team |
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |

**Response:** `200 OK`
```json
{
  "developers": [
    {
      "developer_id": 3,
      "display_name": "Bob",
      "github_username": "bob",
      "team": "Platform",
      "combined_tag_rate": 0.45,
      "pr_tag_rate": 0.50,
      "issue_tag_rate": 0.35,
      "team_average": 0.15,
      "severity": "moderate"
    }
  ]
}
```

Flagged when `combined_tag_rate > team_avg + 1.5 * stddev` or `combined_tag_rate > 0.5`. `severity`: `mild` (1.5-2σ), `moderate` (2-3σ or >50%), `severe` (>3σ or >70%).

### GET /api/stats/communication-scores

Compute a communication score [0-100] per active developer measuring collaboration breadth and depth. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `team` | string | - | Filter to a specific team |
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |

**Response:** `200 OK`
```json
{
  "developers": [
    {
      "developer_id": 2,
      "display_name": "Alice",
      "github_username": "alice",
      "avatar_url": "https://...",
      "team": "Platform",
      "communication_score": 78.5,
      "review_engagement": 22.0,
      "comment_depth": 18.5,
      "reach": 20.0,
      "responsiveness": 18.0
    }
  ]
}
```

Four components (25 points each):
- `review_engagement` — reviews given vs team median
- `comment_depth` — average comment length (200 chars = full marks)
- `reach` — unique developers interacted with / team size
- `responsiveness` — average time to first review (< 24h = full marks)

---

## Slack Integration

Slack notifications via bot token. Admin configures global settings; each developer sets their Slack user ID and notification preferences.

### GET /api/slack/config

Get global Slack configuration. **Admin only.**

**Response:** `200 OK`
```json
{
  "slack_enabled": false,
  "bot_token_configured": false,
  "default_channel": null,
  "notify_stale_prs": true,
  "notify_high_risk_prs": true,
  "notify_workload_alerts": true,
  "notify_sync_failures": true,
  "notify_sync_complete": false,
  "notify_weekly_digest": true,
  "stale_pr_days_threshold": 3,
  "risk_score_threshold": 0.7,
  "digest_day_of_week": 0,
  "digest_hour_utc": 9,
  "stale_check_hour_utc": 9,
  "updated_at": "2026-03-29T10:00:00Z",
  "updated_by": null
}
```

Note: `bot_token` is never returned. `bot_token_configured` indicates whether a token has been set. The bot token is encrypted at rest using Fernet symmetric encryption (requires `ENCRYPTION_KEY` env var).

### PATCH /api/slack/config

Update global Slack configuration. **Admin only.** All fields optional; only provided fields are updated. The `bot_token` is encrypted before storage using Fernet; the plaintext token is never persisted.

**Request body:** Any subset of:
```json
{
  "slack_enabled": true,
  "bot_token": "xoxb-...",
  "default_channel": "#engineering",
  "notify_stale_prs": true,
  "notify_high_risk_prs": true,
  "notify_workload_alerts": true,
  "notify_sync_failures": true,
  "notify_sync_complete": false,
  "notify_weekly_digest": true,
  "stale_pr_days_threshold": 3,
  "risk_score_threshold": 0.7,
  "digest_day_of_week": 0,
  "digest_hour_utc": 9,
  "stale_check_hour_utc": 9
}
```

**Response:** `200 OK` — same shape as GET response.

### POST /api/slack/test

Send a test message to the default channel. **Admin only.** Requires Slack to be enabled with a bot token configured.

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Test message sent to #engineering"
}
```

**Errors:** `403` if Slack disabled, `503` if no bot token configured.

### GET /api/slack/notifications

Get notification history log. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `limit` | int | 50 | Max results (1-200) |
| `offset` | int | 0 | Pagination offset |

**Response:** `200 OK`
```json
{
  "notifications": [
    {
      "id": 1,
      "notification_type": "sync_complete",
      "channel": "#engineering",
      "recipient_developer_id": null,
      "status": "sent",
      "error_message": null,
      "payload": {"text": "Sync completed..."},
      "created_at": "2026-03-29T10:00:00Z"
    }
  ],
  "total": 42
}
```

`notification_type` values: `stale_pr`, `high_risk_pr`, `workload`, `sync_complete`, `sync_failure`, `weekly_digest`, `test`.

### GET /api/slack/user-settings

Get the current authenticated user's Slack notification preferences. **Any authenticated user.**

**Response:** `200 OK`
```json
{
  "developer_id": 2,
  "slack_user_id": "U0123456789",
  "notify_stale_prs": true,
  "notify_high_risk_prs": true,
  "notify_workload_alerts": true,
  "notify_weekly_digest": true
}
```

### PATCH /api/slack/user-settings

Update the current user's Slack notification preferences. **Any authenticated user.** All fields optional.

**Request body:**
```json
{
  "slack_user_id": "U0123456789",
  "notify_stale_prs": false,
  "notify_weekly_digest": true
}
```

**Response:** `200 OK` — same shape as GET response.

### GET /api/slack/user-settings/{developer_id}

Get any developer's Slack notification preferences. **Admin only.**

**Response:** `200 OK` — same shape as user-settings GET.

---

## Notification Center

Unified in-app alert system with materialized notifications, read/dismiss tracking, and admin-configurable thresholds. All endpoints are **admin-only**.

### GET /api/notifications

List active (non-resolved) notifications with read/dismiss state for the current user.

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `severity` | string | — | Filter by severity. **Validated:** must be `critical`, `warning`, or `info` (422 if invalid) |
| `alert_type` | string | — | Filter by alert type. **Validated:** must be a key in `ALERT_TYPE_META` registry (422 if invalid) |
| `include_dismissed` | bool | `false` | Include dismissed notifications |
| `limit` | int | `50` | Max results |
| `offset` | int | `0` | Pagination offset |

**Response:** `200 OK`
```json
{
  "notifications": [
    {
      "id": 1,
      "alert_type": "stale_pr",
      "severity": "critical",
      "title": "PR #42 waiting 72h for review",
      "body": "Fix authentication bug",
      "entity_type": "pull_request",
      "entity_id": 42,
      "link_path": "https://github.com/org/repo/pull/42",
      "developer_id": 5,
      "metadata": {"age_hours": 72.3, "reason": "no_review"},
      "is_read": false,
      "is_dismissed": false,
      "created_at": "2026-03-30T10:00:00Z",
      "updated_at": "2026-03-31T10:00:00Z"
    }
  ],
  "unread_count": 5,
  "counts_by_severity": {"critical": 2, "warning": 2, "info": 1},
  "total": 5
}
```

Sorted by severity priority (critical → warning → info), then newest first.

**Alert types (16):** `stale_pr`, `review_bottleneck`, `underutilized`, `uneven_assignment`, `merged_without_approval`, `revert_spike`, `high_risk_pr`, `bus_factor`, `team_silo`, `isolated_developer`, `declining_trend`, `issue_linkage`, `ai_budget`, `sync_failure`, `unassigned_roles`, `missing_config`.

### POST /api/notifications/{id}/read

Mark a notification as read. Idempotent.

**Response:** `200 OK` — `{"success": true}`

### POST /api/notifications/read-all

Bulk mark all active unread notifications as read.

**Response:** `200 OK` — `{"marked_read": 5}`

### POST /api/notifications/{id}/dismiss

Dismiss a specific notification instance.

**Request body:**
```json
{
  "dismiss_type": "permanent",
  "duration_days": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `dismiss_type` | `"permanent"` or `"temporary"` | Dismiss permanently or for a duration |
| `duration_days` | int or null | Required for temporary. Sets `expires_at`. |

**Response:** `200 OK` — `{"success": true, "expires_at": null}`

### POST /api/notifications/dismiss-type

Dismiss all notifications of an entire alert type. `alert_type` is validated against the `ALERT_TYPE_META` registry (422 if invalid).

**Request body:**
```json
{
  "alert_type": "underutilized",
  "dismiss_type": "temporary",
  "duration_days": 7
}
```

**Response:** `200 OK` — `{"success": true, "alert_type": "underutilized", "expires_at": "2026-04-07T12:00:00Z"}`

### DELETE /api/notifications/dismissals/{id}

Undo a per-instance dismissal (only own dismissals).

**Response:** `200 OK` — `{"success": true}`

### DELETE /api/notifications/type-dismissals/{id}

Undo a per-type dismissal (only own dismissals).

**Response:** `200 OK` — `{"success": true}`

### GET /api/notifications/config

Get notification config (singleton). Includes `alert_types` metadata for the admin UI.

**Response:** `200 OK`
```json
{
  "alert_stale_pr_enabled": true,
  "stale_pr_threshold_hours": 48,
  "review_bottleneck_multiplier": 2.0,
  "revert_spike_threshold_pct": 5.0,
  "high_risk_pr_min_level": "high",
  "issue_linkage_threshold_pct": 20.0,
  "declining_trend_pr_drop_pct": 30.0,
  "declining_trend_quality_drop_pct": 20.0,
  "alert_velocity_declining_enabled": true,
  "alert_scope_creep_high_enabled": true,
  "alert_sprint_at_risk_enabled": true,
  "alert_triage_queue_growing_enabled": true,
  "alert_estimation_accuracy_low_enabled": true,
  "alert_linear_sync_failure_enabled": true,
  "velocity_decline_pct": 20.0,
  "scope_creep_threshold_pct": 25.0,
  "sprint_risk_completion_pct": 50.0,
  "triage_queue_max": 10,
  "triage_duration_hours_max": 48,
  "estimation_accuracy_min_pct": 60.0,
  "exclude_contribution_categories": ["system", "non_contributor"],
  "evaluation_interval_minutes": 15,
  "alert_types": [
    {
      "key": "stale_pr",
      "label": "Stale Pull Requests",
      "description": "PRs waiting too long for review...",
      "enabled": true,
      "thresholds": [{"field": "stale_pr_threshold_hours", "label": "Threshold", "value": 48, "unit": "hours", "min": 1, "max": 720}]
    }
  ],
  "updated_at": "2026-03-31T12:00:00Z",
  "updated_by": "admin"
}
```

### PATCH /api/notifications/config

Partial update notification config. All fields optional.

**Request body:** Any subset of config fields (see GET response).

**Response:** `200 OK` — updated config response.

### POST /api/notifications/evaluate

Trigger alert evaluation on demand.

**Response:** `200 OK`
```json
{
  "created": 3,
  "updated": 1,
  "resolved": 2
}
```

---

## Log Ingestion

Frontend error log ingestion. **No authentication required** — frontend errors can happen before/during auth. Rate-limited to 50 entries per request.

### POST /api/logs/ingest

Receive a batch of frontend log entries and emit them through the backend structlog pipeline (appearing in Loki alongside backend logs).

**Request body:**

```json
{
  "entries": [
    {
      "level": "error",
      "message": "Failed to load dashboard",
      "event_type": "frontend.error",
      "context": {"component": "Dashboard", "status": 500},
      "timestamp": "2026-03-31T12:00:00.000Z",
      "url": "http://localhost:3001/",
      "user_agent": "Mozilla/5.0 ..."
    }
  ]
}
```

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `entries` | `FrontendLogEntry[]` | Yes | — | Max 50 entries processed per request |
| `entries[].level` | `"warn" \| "error"` | No | `"error"` | Maps to structlog warning/error level |
| `entries[].message` | `string` | Yes | — | Log message |
| `entries[].event_type` | `string` | No | `"frontend.error"` | Loki label for filtering |
| `entries[].context` | `object \| null` | No | `null` | Arbitrary key-value context (spread into structlog fields) |
| `entries[].timestamp` | `string \| null` | No | `null` | ISO 8601 timestamp from the frontend |
| `entries[].url` | `string \| null` | No | `null` | Page URL where the error occurred |
| `entries[].user_agent` | `string \| null` | No | `null` | Browser user agent |

**Response:** `204 No Content`

Entries beyond the first 50 are silently dropped. All `context` keys are spread as top-level fields in the structlog output. Each entry is tagged with `source="frontend"` for Loki filtering.

## Integrations

External integration configuration (Linear, future: Jira). All endpoints admin-only. API keys encrypted at rest using Fernet symmetric encryption (requires `ENCRYPTION_KEY` env var).

### POST /api/integrations

Create a new integration configuration. **Admin only.**

**Request body:**
```json
{
  "type": "linear",
  "display_name": "My Linear Workspace",
  "api_key": "lin_api_..."
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `type` | `string` | Yes | Integration type (`"linear"`) |
| `display_name` | `string` | No | Admin-friendly label (max 255) |
| `api_key` | `string` | No | API key (encrypted before storage, max 500) |

**Response:** `201 Created`
```json
{
  "id": 1,
  "type": "linear",
  "display_name": "My Linear Workspace",
  "api_key_configured": true,
  "workspace_id": null,
  "workspace_name": null,
  "status": "active",
  "error_message": null,
  "is_primary_issue_source": false,
  "last_synced_at": null,
  "created_at": "2026-04-06T10:00:00Z",
  "updated_at": "2026-04-06T10:00:00Z"
}
```

Note: `api_key` is never returned in responses. `api_key_configured` indicates whether a key has been set.

### GET /api/integrations

List all configured integrations. **Admin only.**

**Response:** `200 OK` — array of `IntegrationConfigResponse`.

### PATCH /api/integrations/{id}

Update integration configuration. **Admin only.** Only provided fields are updated.

**Request body:**
```json
{
  "display_name": "Updated Name",
  "api_key": "lin_api_new_key",
  "status": "disabled"
}
```

**Response:** `200 OK` — `IntegrationConfigResponse`.

### DELETE /api/integrations/{id}

Remove an integration and all its synced data (cascading delete). **Admin only.**

**Response:** `204 No Content`

### POST /api/integrations/{id}/test

Test the integration connection. **Admin only.**

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "Connected to workspace: My Workspace",
  "workspace_name": "My Workspace"
}
```

### POST /api/integrations/{id}/sync

Trigger a manual sync for this integration. Runs in background. **Admin only.**

**Response:** `202 Accepted`
```json
{
  "message": "Sync started"
}
```

### GET /api/integrations/{id}/status

Get sync status and data counts for this integration. **Admin only.**

**Response:** `200 OK`
```json
{
  "is_syncing": false,
  "last_sync_event_id": 42,
  "last_synced_at": "2026-04-06T12:00:00Z",
  "last_sync_status": "completed",
  "issues_synced": 150,
  "sprints_synced": 8,
  "projects_synced": 3
}
```

### GET /api/integrations/{id}/users

List Linear workspace users for developer identity mapping. **Admin only.**

**Response:** `200 OK`
```json
{
  "users": [
    {
      "id": "linear_user_abc",
      "name": "Jane Doe",
      "display_name": "Jane",
      "email": "jane@example.com",
      "active": true,
      "mapped_developer_id": 5,
      "mapped_developer_name": "Jane Doe"
    }
  ],
  "total": 12,
  "mapped_count": 8,
  "unmapped_count": 4
}
```

### POST /api/integrations/{id}/map-user

Manually map a Linear user to a DevPulse developer. **Admin only.**

**Request body:**
```json
{
  "external_user_id": "linear_user_abc",
  "developer_id": 5
}
```

**Response:** `200 OK`
```json
{
  "id": 1,
  "developer_id": 5,
  "integration_type": "linear",
  "external_user_id": "linear_user_abc",
  "external_email": "jane@example.com",
  "external_display_name": "Jane",
  "mapped_by": "admin",
  "created_at": "2026-04-06T10:00:00Z"
}
```

### GET /api/integrations/issue-source

Get the current primary issue source. **Admin only.**

**Response:** `200 OK`
```json
{
  "source": "github",
  "integration_id": null
}
```

When Linear is set as primary:
```json
{
  "source": "linear",
  "integration_id": 1
}
```

### PATCH /api/integrations/{id}/primary

Set this integration as the primary issue source. Clears primary flag from all other integrations. **Admin only.**

**Response:** `200 OK` — `IntegrationConfigResponse` with `is_primary_issue_source: true`.

## Sprint & Planning Stats

Sprint metrics, planning insights, and project portfolio data from external integrations (Linear). All endpoints admin-only. Requires an active Linear integration with synced data.

### GET /api/sprints

List cycles/sprints. **Admin only.**

**Query params:**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `team_key` | `string` | `null` | Filter by team (e.g., `ENG`) |
| `state` | `string` | `null` | Filter by state: `active`, `closed`, `future` |
| `limit` | `int` | `20` | Max results (1-100) |

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "external_id": "cycle_abc",
    "name": "Sprint 42",
    "number": 42,
    "team_key": "ENG",
    "team_name": "Engineering",
    "state": "closed",
    "start_date": "2026-03-01",
    "end_date": "2026-03-14",
    "planned_scope": 15,
    "completed_scope": 12,
    "cancelled_scope": 2,
    "added_scope": 4,
    "url": "https://linear.app/workspace/cycle/..."
  }
]
```

### GET /api/sprints/{id}

Sprint detail with issues and computed metrics. **Admin only.**

**Response:** `200 OK`
```json
{
  "id": 1,
  "name": "Sprint 42",
  "number": 42,
  "state": "closed",
  "planned_scope": 15,
  "completed_scope": 12,
  "issues": [ /* ExternalIssueResponse[] */ ],
  "completion_rate": 80.0,
  "scope_creep_pct": 26.7
}
```

### GET /api/sprints/velocity

Sprint velocity trend (completed scope per cycle). **Admin only.**

**Query params:** `team_key` (optional), `limit` (default 10).

**Response:** `200 OK`
```json
{
  "data": [
    {
      "sprint_id": 1,
      "sprint_name": "Sprint 40",
      "sprint_number": 40,
      "team_key": "ENG",
      "completed_scope": 12,
      "planned_scope": 15,
      "start_date": "2026-01-01",
      "end_date": "2026-01-14"
    }
  ],
  "avg_velocity": 11.5,
  "trend_direction": "increasing"
}
```

`trend_direction`: `"increasing"`, `"decreasing"`, or `"stable"` (half-split comparison, >10% change threshold).

### GET /api/sprints/completion

Sprint completion rate trend. **Admin only.**

**Query params:** `team_key` (optional), `limit` (default 10).

**Response:** `200 OK`
```json
{
  "data": [
    {
      "sprint_id": 1,
      "sprint_name": "Sprint 40",
      "sprint_number": 40,
      "planned_scope": 15,
      "completed_scope": 12,
      "completion_rate": 80.0
    }
  ],
  "avg_completion_rate": 78.5
}
```

### GET /api/sprints/scope-creep

Scope creep trend (mid-cycle additions as % of planned). **Admin only.**

**Query params:** `team_key` (optional), `limit` (default 10).

**Response:** `200 OK`
```json
{
  "data": [
    {
      "sprint_id": 1,
      "sprint_name": "Sprint 40",
      "sprint_number": 40,
      "planned_scope": 15,
      "added_scope": 4,
      "scope_creep_pct": 26.7
    }
  ],
  "avg_scope_creep_pct": 22.3
}
```

### GET /api/projects

List external projects with health and issue counts. **Admin only.**

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "external_id": "proj_abc",
    "key": "platform",
    "name": "Platform Rewrite",
    "status": "started",
    "health": "on_track",
    "start_date": "2026-01-01",
    "target_date": "2026-06-30",
    "progress_pct": 0.45,
    "lead_id": 5,
    "url": "https://linear.app/workspace/project/...",
    "issue_count": 42,
    "completed_issue_count": 28
  }
]
```

### GET /api/projects/{id}

Project detail with issues. **Admin only.**

**Response:** `200 OK` — `ExternalProjectDetailResponse` with `issues: ExternalIssueResponse[]`.

### GET /api/planning/triage

Triage queue metrics. **Admin only.**

**Query params:** `date_from` (optional), `date_to` (optional).

**Response:** `200 OK`
```json
{
  "avg_triage_duration_s": 14400.0,
  "median_triage_duration_s": 10800.0,
  "p90_triage_duration_s": 28800.0,
  "issues_in_triage": 3,
  "total_triaged": 45
}
```

### GET /api/planning/alignment

Work alignment — linked vs unlinked PRs. **Admin only.**

**Query params:** `date_from` (optional), `date_to` (optional).

**Response:** `200 OK`
```json
{
  "total_prs": 100,
  "linked_prs": 72,
  "unlinked_prs": 28,
  "alignment_pct": 72.0
}
```

### GET /api/planning/accuracy

Estimation accuracy trend (estimated vs completed points per cycle). **Admin only.**

**Query params:** `team_key` (optional), `limit` (default 10).

**Response:** `200 OK`
```json
{
  "data": [
    {
      "sprint_id": 1,
      "sprint_name": "Sprint 40",
      "sprint_number": 40,
      "estimated_points": 25.0,
      "completed_points": 20.0,
      "accuracy_pct": 80.0
    }
  ],
  "avg_accuracy_pct": 76.5
}
```

### GET /api/planning/correlation

Planning vs delivery correlation (sprint completion rate vs avg PR merge time). **Admin only.**

**Query params:** `team_key` (optional), `limit` (default 10).

**Response:** `200 OK`
```json
{
  "data": [
    {
      "sprint_id": 1,
      "sprint_name": "Sprint 40",
      "completion_rate": 80.0,
      "avg_pr_merge_time_hours": 12.5
    }
  ],
  "correlation_coefficient": -0.65
}
```

`correlation_coefficient`: Pearson r (-1 to 1). Negative = higher completion correlates with faster merge times. `null` if fewer than 3 data points.

### GET /api/developers/{developer_id}/sprint-summary

Active sprint + recent completion data for a developer. Returns empty data when developer is not mapped to Linear or Linear is not configured. **Admin only.**

**Response:** `200 OK`
```json
{
  "active_sprint": {
    "sprint_id": 5,
    "name": "Sprint 24",
    "start_date": "2026-03-25",
    "end_date": "2026-04-08",
    "total_issues": 10,
    "completed_issues": 6,
    "completion_pct": 60.0,
    "days_remaining": 1,
    "on_track": true
  },
  "recent_sprints": [
    {
      "sprint_id": 4,
      "name": "Sprint 23",
      "total_issues": 8,
      "completed_issues": 7,
      "completion_pct": 87.5
    }
  ]
}
```

`active_sprint`: `null` if no active sprint or developer has no issues in it. `on_track`: true if `completion_pct >= elapsed_pct`. `recent_sprints`: last 3 closed sprints where the developer had assigned issues.

### GET /api/developers/{developer_id}/linear-issues

Linear issues assigned to a developer. **Admin only.**

**Query params:**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `status_category` | `string` | `null` | Comma-separated: `todo`, `in_progress`, `done` |
| `limit` | `int` | `20` | Max results (1-100) |

**Response:** `200 OK`
```json
[
  {
    "id": 42,
    "identifier": "ENG-456",
    "title": "Fix auth timeout",
    "status": "In Progress",
    "status_category": "in_progress",
    "priority": 1,
    "priority_label": "Urgent",
    "estimate": 3.0,
    "url": "https://linear.app/workspace/issue/ENG-456",
    "sprint_id": 5
  }
]
```

## Linear Insights v2

Endpoints added by the Linear Insights v2 epic. All read-only analytics on top of the
expanded Linear sync (Phase 01 comments/history/attachments/relations) + GitHub PR timeline
(Phase 09).

### Phase 02 — Linkage Quality (admin)

#### GET /api/integrations/{integration_id}/linkage-quality

Admin-only summary of PR↔Linear-issue linkage health. Used by `/admin/linkage-quality`.

**Response:** `200 OK`
```json
{
  "total_prs": 1248,
  "linked_prs": 832,
  "linkage_rate": 0.667,
  "by_confidence": {"high": 540, "medium": 250, "low": 78},
  "by_source": {
    "linear_attachment": 540,
    "branch": 180,
    "title": 70,
    "body": 78
  },
  "unlinked_recent": [
    {
      "pr_id": 1234,
      "number": 567,
      "title": "Bump deps",
      "created_at": "2026-04-21T08:15:00Z",
      "html_url": "https://github.com/acme/repo/pull/567",
      "author_github_username": "alice",
      "repo": "acme/repo"
    }
  ],
  "disagreement_prs": [
    {
      "pr_id": 999,
      "number": 42,
      "title": "Fix auth",
      "html_url": "https://github.com/acme/repo/pull/42",
      "repo": "acme/repo",
      "links": [
        {"external_issue_id": 5, "identifier": "ENG-100", "link_source": "title", "link_confidence": "medium"},
        {"external_issue_id": 7, "identifier": "ENG-200", "link_source": "branch", "link_confidence": "medium"}
      ]
    }
  ]
}
```

`unlinked_recent` is capped at 50, filtered to PRs created in the last 30 days. `disagreement_prs`
lists PRs with multiple issue links at the same confidence tier.

#### POST /api/integrations/{integration_id}/relink

Rerun the 4-pass linker (attachment → branch → title → body). Idempotent; upgrades
existing links to higher confidence when a stronger signal is found. **Admin only.**

**Response:** `200 OK`
```json
{"sync_event_id": 42, "status": "completed", "new_links": null}
```

Writes a `SyncEvent` with `sync_type="linear"`, `sync_scope="Linear PR relink"`.
Poll `/api/sync/events/{sync_event_id}` for detail.

### Phase 03 — Linear Usage Health

#### GET /api/linear/usage-health?date_from={ISO}&date_to={ISO}

Five-signal dashboard card. Returns `409 Conflict` when Linear is not configured as
primary issue source — frontend treats this as "hide the card, don't show error".

**Query params:**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `date_from` | `datetime` | now - 30d | ISO 8601 |
| `date_to` | `datetime` | now | ISO 8601 |

**Response:** `200 OK`
```json
{
  "adoption": {
    "linked_pr_count": 480,
    "total_pr_count": 650,
    "linkage_rate": 0.738,
    "target": 0.70,
    "status": "healthy"
  },
  "spec_quality": {
    "median_description_length": 180,
    "median_comments_before_first_pr": 2.5,
    "high_comment_issue_pct": 0.08,
    "status": "healthy"
  },
  "autonomy": {
    "self_picked_count": 120,
    "pushed_count": 80,
    "self_picked_pct": 0.60,
    "median_time_to_assign_s": 7200,
    "status": "healthy"
  },
  "dialogue_health": {
    "median_comments_per_issue": 2.0,
    "p90_comments_per_issue": 9,
    "silent_issue_pct": 0.15,
    "distribution_shape": "healthy",
    "status": "healthy"
  },
  "creator_outcome": {
    "top_creators": [
      {
        "developer_id": 5,
        "developer_name": "Alice",
        "issues_created": 12,
        "avg_comments_on_their_issues": 1.8,
        "avg_downstream_pr_review_rounds": 1.2,
        "sample_size": 8
      }
    ]
  }
}
```

`status` values on each signal: `healthy` | `warning` | `critical`. Low-sample rows
(`sample_size < 5`) should be badged in the UI.

### Phase 04 — Issue Conversations

All endpoints require authentication (not admin-only). Date-range optional; defaults
to last 30 days.

#### GET /api/conversations/chattiest

Top-N issues by non-system comment count with filters.

**Query params:**

| Param | Type | Default |
|-------|------|---------|
| `date_from` | `datetime` | now - 30d |
| `date_to` | `datetime` | now |
| `limit` | `int` | 20 (max 200) |
| `project_id` | `int` | null |
| `creator_id` | `int` | null |
| `assignee_id` | `int` | null |
| `label` | `string` | null (exact-match on issue labels) |
| `priority` | `int` | null |
| `has_linked_pr` | `bool` | null |

**Response:** `200 OK`
```json
[
  {
    "issue_id": 42,
    "identifier": "ENG-100",
    "title": "Auth timeout",
    "url": "https://linear.app/...",
    "creator": {"id": 5, "name": "Alice"},
    "assignee": {"id": 6, "name": "Bob"},
    "project": {"id": 2, "name": "Platform"},
    "priority_label": "High",
    "estimate": 3.0,
    "comment_count": 14,
    "unique_participants": 5,
    "first_response_s": 3600,
    "created_at": "2026-04-01T10:00:00Z",
    "status": "In Progress",
    "linked_prs": [
      {"pr_id": 99, "number": 123, "repo": "acme/repo", "review_round_count": 4, "merged_at": null}
    ],
    "avg_linked_pr_review_rounds": 4.0
  }
]
```

#### GET /api/conversations/scatter

Scatter points for comment-count vs review-round correlation.

**Response:** `200 OK`
```json
[{"comment_count": 14, "review_rounds": 4, "issue_identifier": "ENG-100", "pr_number": 123}]
```

#### GET /api/conversations/first-response

Histogram buckets for time-to-first-non-creator-non-system comment.

**Response:** `200 OK`
```json
[
  {"bucket": "<1h", "count": 42},
  {"bucket": "1-4h", "count": 58},
  {"bucket": "4-12h", "count": 30},
  {"bucket": "12h-1d", "count": 18},
  {"bucket": "1-3d", "count": 11},
  {"bucket": "3-7d", "count": 5},
  {"bucket": ">168h", "count": 2},
  {"bucket": "never", "count": 14}
]
```

#### GET /api/conversations/participants

Distribution of unique non-system comment authors per issue.

**Response:** `200 OK`
```json
[
  {"participants": "1", "count": 62},
  {"participants": "2", "count": 41},
  {"participants": "3", "count": 28},
  {"participants": "4-5", "count": 15},
  {"participants": "6+", "count": 4}
]
```

### Phase 05 — Developer Linear profiles

All require **self or admin** — 403 otherwise. Used by Developer Detail page.

#### GET /api/developers/{developer_id}/linear-creator-profile

**Response:** `200 OK`
```json
{
  "issues_created": 24,
  "issues_created_by_type": {"bug": 8, "feature": 10, "tech_debt": 4, "unknown": 2},
  "top_labels": [{"label": "backend", "count": 12}, {"label": "auth", "count": 7}],
  "avg_description_length": 220,
  "avg_comments_generated": 1.9,
  "avg_downstream_pr_review_rounds": 1.4,
  "sample_size_downstream_prs": 18,
  "self_assigned_pct": 0.45,
  "median_time_to_close_for_their_issues_s": 345600
}
```

#### GET /api/developers/{developer_id}/linear-worker-profile

**Response:** `200 OK`
```json
{
  "issues_worked": 32,
  "self_picked_count": 14,
  "pushed_count": 18,
  "self_picked_pct": 0.437,
  "median_triage_to_start_s": 172800,
  "median_cycle_time_s": 259200,
  "issues_worked_by_status": {"todo": 3, "in_progress": 5, "done": 24},
  "reassigned_to_other_count": 2
}
```

#### GET /api/developers/{developer_id}/linear-shepherd-profile

**Response:** `200 OK`
```json
{
  "comments_on_others_issues": 87,
  "issues_commented_on": 42,
  "unique_teams_commented_on": 3,
  "is_shepherd": true,
  "top_collaborators": [
    {"developer_id": 6, "name": "Bob", "count": 22}
  ]
}
```

`is_shepherd` = comments_on_others > max(3 × team_median, 10).

### Phase 06 — Flow Analytics

Driven by `external_issue_history` (Phase 01). Feature-gated by readiness.

#### GET /api/flow/readiness

**Response:** `200 OK`
```json
{
  "ready": true,
  "days_of_history": 28,
  "issues_with_history": 142,
  "threshold_days": 14,
  "threshold_issues": 100
}
```

#### GET /api/flow/status-distribution?date_from&date_to&group_by=all|project|team

p50/p75/p90/p95 time-in-state per status category.

**Response:** `200 OK`
```json
[
  {"status_category": "triage", "p50_s": 3600, "p75_s": 14400, "p90_s": 86400, "p95_s": 172800, "sample_size": 120},
  {"status_category": "in_progress", "p50_s": 86400, "p75_s": 259200, "p90_s": 604800, "p95_s": 1209600, "sample_size": 95}
]
```

#### GET /api/flow/regressions

Issues that transitioned backwards (in_review → in_progress, etc.).

#### GET /api/flow/triage-bounces

Issues that left triage, then re-entered triage.

#### GET /api/flow/refinement-churn

Distribution + top-20 outliers for estimate/priority/project churn before issue start.

**Response:** `200 OK`
```json
{
  "distribution": {"p50": 1, "p90": 4, "mean": 1.8, "total_issues_with_churn": 72},
  "top": [{"issue_id": 42, "identifier": "ENG-100", "title": "...", "url": "...", "churn_events": 7}]
}
```

### Phase 07 — Bottlenecks

All endpoints require authentication.

#### GET /api/bottlenecks/summary

Top 5 active bottlenecks digest for the dashboard/summary card.

**Response:** `200 OK`
```json
[
  {
    "title": "Review load imbalance",
    "severity": "warning",
    "detail": "8 reviewers; top 3 handle 54% of reviews (Gini 0.62)",
    "drill_path": "/insights/bottlenecks#review-load"
  }
]
```

Severity: `info` | `warning` | `critical`. Summary picks deterministically from: Gini > 0.4,
any dev WIP > 4, blocked chain depth ≥ 3, any open ping-pong PR, cross-team handoffs > 5.

#### GET /api/bottlenecks/cumulative-flow?cycle_id&project_id&date_from&date_to

Per-day issue count by status category — CFD stacked-area data.

#### GET /api/bottlenecks/wip?threshold=4

Developers with >threshold in_progress issues, with the list of offending issues.

#### GET /api/bottlenecks/review-load

**Response:** `200 OK`
```json
{
  "gini": 0.62,
  "total_reviews": 432,
  "total_reviewers": 8,
  "top_k_share": 0.54,
  "top_reviewers": [{"reviewer_id": 5, "reviewer_name": "Alice", "review_count": 92}]
}
```

#### GET /api/bottlenecks/review-network

Nodes + weighted edges for reviewer→author graph. Client computes community detection.

#### GET /api/bottlenecks/cross-team-handoffs

Issues that moved between cycles belonging to different teams.

#### GET /api/bottlenecks/blocked-chains

Open issues with blocked-by chain depth ≥ 2, sorted depth-desc.

#### GET /api/bottlenecks/ping-pong

PRs with `review_round_count > 3` in range.

#### GET /api/bottlenecks/bus-factor-files?since_days=90&min_authors=2

Files with fewer than `min_authors` distinct PR authors in the last `since_days` days.

#### GET /api/bottlenecks/cycle-histogram

Cycle-time distribution with bimodality detection.

**Response:** `200 OK`
```json
{
  "sample_size": 142,
  "p50_s": 86400,
  "p90_s": 604800,
  "bimodal_analysis": {
    "is_bimodal": true,
    "peaks": [{"bin": 2, "count": 35}, {"bin": 7, "count": 28}],
    "trough_ratio": 0.42,
    "bins": [3, 12, 35, 18, 8, 4, 10, 28, 15, 9],
    "bucket_size": 120000.0,
    "min": 3600.0,
    "max": 1296000.0
  }
}
```

### Phase 10 — DORA v2

#### GET /api/dora/v2?date_from&date_to&cohort=all|human|ai_reviewed|ai_authored|hybrid

**Response:** `200 OK`
```json
{
  "throughput": {
    "deployment_frequency": 0.42,
    "lead_time_hours": 18.5,
    "mttr_hours": 2.3
  },
  "stability": {
    "change_failure_rate": 6.8,
    "rework_rate": 8.2
  },
  "bands": {
    "deployment_frequency": "high",
    "lead_time": "elite",
    "mttr": "elite",
    "change_failure_rate": "high",
    "rework_rate": "high",
    "overall": "high"
  },
  "cohorts": {
    "human": {"merges": 210, "rework_rate": 7.1, "share_pct": 75.0},
    "ai_reviewed": {"merges": 60, "rework_rate": 10.0, "share_pct": 21.4},
    "ai_authored": {"merges": 6, "rework_rate": 16.7, "share_pct": 2.1},
    "hybrid": {"merges": 4, "rework_rate": 25.0, "share_pct": 1.4}
  },
  "date_from": "2026-03-22T...",
  "date_to": "2026-04-22T..."
}
```

Bands use DORA 2024 thresholds (elite/high/medium/low). Rework rate = % of merged PRs
followed by another merged PR touching shared files within 7 days.

The existing `/api/stats/dora` endpoint is preserved unchanged; `/api/dora/v2` is additive.

### Phase 11 — Metrics Governance

#### GET /api/metrics/catalog

Registry of all exposed metrics (for frontend tooltips, pairing, visibility hints)
plus the banned-metric list.

**Response:** `200 OK`
```json
{
  "metrics": [
    {
      "key": "avg_downstream_pr_review_rounds",
      "label": "Avg downstream PR review rounds (by ticket creator)",
      "category": "quality",
      "is_activity": false,
      "paired_outcome_key": null,
      "visibility_default": "self",
      "is_distribution": false,
      "goodhart_risk": "high",
      "goodhart_notes": "Creator-outcome correlation. Default self+admin visibility...",
      "description": ""
    }
  ],
  "banned": [
    {"key": "lines_of_code_per_dev", "reason": "LOC is not a productivity metric..."}
  ]
}
```

`visibility_default`: `self` | `team` | `admin`. `category`: `throughput` | `stability` |
`flow` | `dialogue` | `bottleneck` | `quality`. `goodhart_risk`: `low` | `medium` | `high`.
