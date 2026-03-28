# Task P2-02: Review Round-Trip Count

## Phase
Phase 2 — Make It Smart

## Status
completed

## Blocked By
- 04-github-sync-service
- M1-review-quality-signals

## Blocks
None

## Description
Track how many review cycles (changes_requested -> re-review) each PR goes through. This is arguably the best single indicator of process health — it reflects PR description quality, requirements clarity, and reviewer-author alignment. Currently, the system cannot distinguish a PR merged on first pass from one with 5 rounds of iteration.

## Deliverables

### Database migration
Add column to `pull_requests`:
- `review_round_count` (Integer, default 0) — number of distinct `CHANGES_REQUESTED` reviews on this PR

### backend/app/services/github_sync.py (extend)
After syncing all reviews for a PR (in `sync_repo`, after the reviews loop), compute:
```python
review_round_count = count of pr_reviews WHERE pr_id = this_pr AND state = 'CHANGES_REQUESTED'
```

Update the PR row with this count. Recompute on every sync to stay accurate.

### backend/app/services/stats.py (extend)
Add to `get_developer_stats()`:
- `avg_review_rounds` (float) — average `review_round_count` across authored PRs merged in period
- `prs_merged_first_pass` (int) — count of merged PRs with `review_round_count == 0`
- `first_pass_rate` (float) — `prs_merged_first_pass / prs_merged` (percentage merged without changes requested)

Add to `get_team_stats()`:
- `avg_review_rounds` — team average
- `first_pass_rate` — team average

Add to `get_benchmarks()`:
- `review_rounds` as a new benchmarked metric with p25/p50/p75 (lower is better)

### backend/app/schemas/schemas.py (extend)
- Add `avg_review_rounds: float | None` to `DeveloperStatsResponse`
- Add `prs_merged_first_pass: int` and `first_pass_rate: float | None` to `DeveloperStatsResponse`
- Add `avg_review_rounds: float | None` to `TeamStatsResponse`

## Key Insight
Teams with high review round counts should investigate:
- Are PR descriptions unclear? (Add PR templates)
- Are requirements ambiguous? (Improve issue quality — see P3-03)
- Is there misalignment between reviewer expectations and author approach? (Better upfront design discussion)
