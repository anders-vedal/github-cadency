# Task P2-05: Capture PR Labels, Merged-By, Branch Names

## Phase
Phase 2 — Make It Smart

## Status
done

## Blocked By
- 04-github-sync-service

## Blocks
- P2-06-revert-detection
- P3-05-pr-risk-scoring

## Description
Capture four fields from the GitHub API response that are already fetched but never stored: PR labels, merged-by username, head branch, and base branch. These are prerequisites for revert detection, hotfix identification, work categorization, and branch pattern analysis.

## Deliverables

### Database migration
Add columns to `pull_requests`:
- `labels` (JSONB, nullable) — array of label name strings, matching the `Issue.labels` pattern
- `merged_by_username` (String(255), nullable) — GitHub login of the user who merged the PR
- `head_branch` (String(255), nullable) — source branch name (e.g., `feature/add-auth`)
- `base_branch` (String(255), nullable) — target branch name (e.g., `main`)

### backend/app/services/github_sync.py (extend)
In `upsert_pull_request()`, add field extraction from the already-fetched API response:

```python
labels = [l["name"] for l in pr_data.get("labels", [])]
head_branch = pr_data.get("head", {}).get("ref")
base_branch = pr_data.get("base", {}).get("ref")
```

For `merged_by_username`: this is available in the PR detail response (already fetched at lines 216-233 for open PRs and PRs missing size data). Extract from:
```python
merged_by_username = detail.get("merged_by", {}).get("login") if detail else None
```

### Self-merge detection
Add computed field:
- `is_self_merged` (Boolean, default False) — True if `merged_by_username == author.github_username`

Compute at sync time after both fields are available.

### backend/app/services/stats.py (extend)
Add to `get_developer_stats()`:
- `prs_self_merged` (int) — count of merged PRs where author == merger
- `self_merge_rate` (float) — `prs_self_merged / prs_merged`

### backend/app/schemas/schemas.py (extend)
- Add `prs_self_merged: int` and `self_merge_rate: float | None` to `DeveloperStatsResponse`

## Key Design Decisions
- PR labels mirror the existing `Issue.labels` JSONB pattern for consistency
- `merged_by_username` is a denormalized string (not a FK to developers) because the merger may be an external contributor or bot
- `head_branch` and `base_branch` enable future branch pattern analysis and hotfix detection
