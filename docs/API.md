# DevPulse API Reference

Base URL: `http://localhost:8000/api`

## Authentication

DevPulse uses GitHub OAuth for authentication. After login, all protected endpoints require a JWT:
```
Authorization: Bearer {jwt_token}
```

**Two roles:**
- `admin` — full access to all endpoints
- `developer` — read-only access to own stats, profile, goals, and repo stats

**Public endpoints** (no auth required): `GET /api/health`, `POST /api/webhooks/github`, `GET /api/auth/login`, `GET /api/auth/callback`

### Access Control Summary

| Endpoint Group | Admin | Developer |
|----------------|-------|-----------|
| **Auth** (`/api/auth/*`) | Public | Public |
| **Developer stats** (`/api/stats/developer/{id}`) | Any ID | Own ID only |
| **Developer trends** (`/api/stats/developer/{id}/trends`) | Any ID | Own ID only |
| **Team/benchmarks/workload/collaboration/collaboration-trends/stale-prs/issue-linkage/issue-quality/issue-creators** | Yes | No (403) |
| **Code churn** (`/api/stats/repo/{id}/churn`) | Yes | No (403) |
| **PR risk** (`/api/stats/pr/{id}/risk`, `/api/stats/risk-summary`) | Yes | No (403) |
| **CI/CD stats** (`/api/stats/ci`) | Yes | No (403) |
| **Repo stats** (`/api/stats/repo/{id}`) | Yes | Yes |
| **Developers CRUD** (`/api/developers/*`) | Full access | GET own profile only |
| **Goals** (`/api/goals/*`) | Full access | GET own goals, POST/PATCH self-goals |
| **Goal progress** (`/api/goals/{id}/progress`) | Any goal | Own goals only |
| **Sync** (`/api/sync/*`) | Yes | No (403) |
| **AI Analysis** (`/api/ai/*`) | Yes | No (403) |

Date parameters accept ISO 8601 format: `2026-01-01T00:00:00Z`. When `date_from`/`date_to` are omitted, defaults to the last 30 days.

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
- New user → creates developer record (`app_role: "developer"`, or `"admin"` if username matches `DEVPULSE_INITIAL_ADMIN`)
- Existing user → updates `avatar_url`
- Deactivated user → returns `403 Forbidden`

**Response:** `302 Redirect` to `{FRONTEND_URL}/auth/callback?token={jwt}`

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

`role` values: `developer`, `senior_developer`, `lead`, `architect`, `devops`, `qa`, `intern`

**Response:** `201 Created` — `DeveloperResponse`
**Errors:** `409 Conflict` if `github_username` already exists

### GET /api/developers/{developer_id}

**Access:** Admin can view any developer. Developers can view their own profile only.

**Response:** `200 OK` — `DeveloperResponse`
**Errors:** `404 Not Found`, `403 Forbidden` (developer accessing another profile)

### PATCH /api/developers/{developer_id}

Partial update. Only provided fields are changed. **Admin only.**

**Request Body:** Any subset of `DeveloperCreate` fields (except `github_username`), plus:
- `app_role`: `"admin"` or `"developer"` — promotes or demotes a user

**Response:** `200 OK` — `DeveloperResponse`

### DELETE /api/developers/{developer_id}

Soft-delete: sets `is_active = false`. **Admin only.** Deactivated developers cannot log in via OAuth.

**Response:** `204 No Content`

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

### GET /api/stats/benchmarks

Team percentile bands (p25/p50/p75) across all active developers. **Admin only.**

| Query Param | Type | Default | Description |
|-------------|------|---------|-------------|
| `date_from` | datetime | 30 days ago | Period start |
| `date_to` | datetime | now | Period end |
| `team` | string | - | Filter by team |

**Response:** `200 OK`
```json
{
  "period_start": "2026-02-26T00:00:00Z",
  "period_end": "2026-03-28T00:00:00Z",
  "sample_size": 15,
  "team": null,
  "metrics": {
    "time_to_merge_h": { "p25": 8.5, "p50": 16.2, "p75": 28.0 },
    "time_to_first_review_h": { "p25": 1.2, "p50": 3.8, "p75": 8.5 },
    "prs_merged": { "p25": 3.0, "p50": 7.0, "p75": 12.0 },
    "review_turnaround_h": { "p25": 2.0, "p50": 5.5, "p75": 12.0 },
    "reviews_given": { "p25": 4.0, "p50": 10.0, "p75": 18.0 },
    "additions_per_pr": { "p25": 50.0, "p50": 150.0, "p75": 400.0 }
  }
}
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

DORA metrics: deployment frequency and change lead time from GitHub Actions workflow runs. Only returns data when `DEPLOY_WORKFLOW_NAME` is configured. **Admin only.**

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
  "period_days": 30,
  "deployments": [
    {
      "id": 42,
      "repo_name": "org/api-service",
      "environment": "production",
      "sha": "abc123def456789...",
      "deployed_at": "2026-03-27T14:30:00Z",
      "workflow_name": "deploy-production",
      "status": "success",
      "lead_time_hours": 4.25
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `deploy_frequency` | Successful deployments per day in the period (`total_deployments / period_days`) |
| `deploy_frequency_band` | DORA benchmark classification: `elite` (>1/day), `high` (daily–weekly), `medium` (weekly–monthly), `low` (<monthly) |
| `avg_lead_time_hours` | Average hours from oldest undeployed merged PR to deployment. `null` if no lead time data |
| `lead_time_band` | DORA benchmark classification: `elite` (<1h), `high` (<1 day), `medium` (<1 week), `low` (>1 week) |
| `total_deployments` | Count of successful deployments in the period |
| `period_days` | Number of days in the queried date range |
| `deployments` | Last 20 successful deployments in the period, ordered by `deployed_at` descending |

**Deployment detail fields:**

| Field | Description |
|-------|-------------|
| `id` | Deployment record ID |
| `repo_name` | Repository full name (e.g. `org/repo`) |
| `environment` | Deployment environment (from `DEPLOY_ENVIRONMENT` config, default `"production"`) |
| `sha` | Deployed commit SHA |
| `deployed_at` | Deployment completion timestamp (ISO 8601) |
| `workflow_name` | GitHub Actions workflow name |
| `status` | Deployment status (`"success"`) |
| `lead_time_hours` | Hours from oldest undeployed merged PR to this deployment. `null` for the first deployment (no prior reference) |

**Configuration:** Deployment sync requires the `DEPLOY_WORKFLOW_NAME` environment variable to be set to the exact name of the GitHub Actions workflow that represents a production deployment. If empty, no deployments are synced and this endpoint returns zero values.

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
  "since": "2026-01-01T00:00:00Z"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sync_type` | `"full"` \| `"incremental"` | `"incremental"` | Full re-syncs all data; incremental fetches since each repo's `last_synced_at` |
| `repo_ids` | `int[]` \| `null` | `null` | Specific repo IDs to sync. `null` = all tracked repos |
| `since` | `datetime` \| `null` | `null` | Override per-repo `last_synced_at` with a uniform date |

**Response:** `202 Accepted`
```json
{ "status": "accepted", "sync_type": "incremental" }
```

**Error:** `409 Conflict` — a sync is already in progress.

### POST /api/sync/resume/{event_id}

Resume an interrupted sync, processing only repos that were not completed in the original run.

**Path Params:** `event_id` (int) — ID of the failed/partial sync event to resume.

**Response:** `202 Accepted`
```json
{ "status": "accepted", "remaining_repos": 5 }
```

**Errors:**
- `404` — sync event not found
- `400` — event is not resumable or no remaining repos
- `409` — a sync is already in progress

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
    "is_resumable": false,
    "resumed_from_id": null,
    "started_at": "2026-03-28T10:30:00Z",
    "completed_at": null,
    "duration_s": null
  },
  "last_completed": null,
  "tracked_repos_count": 42,
  "total_repos_count": 50,
  "last_successful_sync": "2026-03-27T10:30:00Z",
  "last_sync_duration_s": 1234
}
```

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
- `repos_completed` — list of `{repo_id, repo_name, status, prs, issues, warnings}`
- `repos_failed` — list of `{repo_id, repo_name, error}`
- `errors` — structured error objects (see below)
- `log_summary` — condensed sync log entries `{ts, level, msg, repo?}`
- `is_resumable` — `true` if sync can be resumed via `POST /sync/resume/{id}`
- `resumed_from_id` — links to the original interrupted sync event
- `rate_limit_wait_s` — total seconds spent waiting for GitHub rate limits

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
  "date_to": "2026-03-01T00:00:00Z"
}
```

`analysis_type`: `communication`, `conflict`, `sentiment`
`scope_type`: `developer`, `team`, `repo`
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
  "date_to": "2026-03-01T00:00:00Z"
}
```

**Context gathered:** developer stats, 4-period trends, team benchmarks, PR list, review quality tiers, active goals with progress, previous 1:1 brief (for continuity), issue creator stats with team averages (if developer has created issues in the period).

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
  "date_to": "2026-03-01T00:00:00Z"
}
```

`team` is optional — omit for all active developers.

**Context gathered:** team stats + benchmarks, workload balance + alerts, collaboration matrix + insights, CHANGES_REQUESTED reviews with body text + metadata (up to 60), heated issue threads with full chronological dialogue (3+ comments between 2 tracked devs), active team goals with current values.

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

Estimate token usage and cost for an AI call without executing it. Does not call Claude.

| Query Param | Type | Required | Description |
|-------------|------|----------|-------------|
| `feature` | string | Yes | `general_analysis`, `one_on_one_prep`, `team_health`, `work_categorization` |
| `scope_type` | string | No | `developer`, `team`, `repo` (for general_analysis) |
| `scope_id` | string | No | Entity ID (for general_analysis) |
| `date_from` | datetime | No | Period start (defaults to 30 days ago) |
| `date_to` | datetime | No | Period end (defaults to now) |

**Response:** `200 OK`
```json
{
  "estimated_input_tokens": 5000,
  "estimated_output_tokens": 3000,
  "estimated_cost_usd": 0.06,
  "data_items": 45,
  "note": "Based on 45 data items in scope"
}
```

Estimation methods vary by feature:
- `general_analysis`: Gathers actual data items and estimates tokens from volume
- `one_on_one_prep`: Fixed estimate (~5K input, ~3K output) based on typical context size
- `team_health`: Scales by active developer count (~200 tokens per dev + 3K base)
- `work_categorization`: Max batch estimate (200 items)
