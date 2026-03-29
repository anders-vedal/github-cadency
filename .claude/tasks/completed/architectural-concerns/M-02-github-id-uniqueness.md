# Task M-02: Add Unique Constraints on `github_id` Columns

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
`pr_reviews.github_id`, `pr_review_comments.github_id`, and `issue_comments.github_id` all have `unique=True`. However, `pull_requests.github_id` and `issues.github_id` do not. The upsert pattern uses `(repo_id, number)` as the composite key, so uniqueness on `github_id` is not strictly required for correctness — but the inconsistency means duplicate GitHub IDs could theoretically exist without any DB-level guard.

### Options
1. **Add unique constraints** to `pull_requests.github_id` and `issues.github_id` for consistency
2. **Document as intentional** if the composite key pattern is preferred and the overhead of a unique index is unwanted

Option 1 is recommended — GitHub IDs are globally unique, and the index also helps with any future lookups by `github_id`.

### Files
- `backend/app/models/models.py` — add `unique=True` to `github_id` on `PullRequest` and `Issue`
- `backend/migrations/versions/` — new migration

### Architecture Docs
- `docs/architecture/DATA-MODEL.md` — Tables section and Architectural Concerns
