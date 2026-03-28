# Task P2-06: Revert PR Detection

## Phase
Phase 2 — Make It Smart

## Status
done

## Blocked By
- P2-05-pr-metadata-capture

## Blocks
None

## Description
Detect reverted PRs by parsing PR titles and bodies for GitHub's standard revert signature. A reverted PR is one of the strongest quality signals in software engineering — it means code passed review but was broken enough to require rollback. This is ~30 lines of new code with very high signal value.

## Deliverables

### Database migration
Add columns to `pull_requests`:
- `is_revert` (Boolean, default False) — True if this PR reverts another PR
- `reverted_pr_number` (Integer, nullable) — the PR number that was reverted (parsed from title)

### backend/app/services/github_sync.py (extend)
New helper function: `detect_revert(title: str, body: str) -> tuple[bool, int | None]`
- Check if title matches pattern: `Revert "..."` or `Revert #NNN`
- Check if body contains `This reverts commit`
- If revert detected, extract the original PR number from the title pattern `Revert "<original title>"` by looking up the original title in the same repo, OR from PR body references
- Returns `(is_revert, reverted_pr_number)`

Call in `upsert_pull_request()` to set `is_revert` and `reverted_pr_number`.

### backend/app/services/stats.py (extend)
Add to `get_developer_stats()`:
- `prs_reverted` (int) — count of PRs authored by this developer that were subsequently reverted by another PR
- `reverts_authored` (int) — count of revert PRs this developer created (positive signal: fixing problems quickly)

Add to `get_team_stats()`:
- `revert_rate` (float) — reverted PRs / total merged PRs for the team

### backend/app/schemas/schemas.py (extend)
- Add `prs_reverted: int` to `DeveloperStatsResponse`
- Add `reverts_authored: int` to `DeveloperStatsResponse`
- Add `revert_rate: float | None` to `TeamStatsResponse`

### Alert integration
Add new `WorkloadAlert` type: `revert_spike`
- Trigger when revert rate exceeds 5% in the period
- Message: "Revert rate is {rate}% ({count} reverts out of {total} merged PRs)"

## Testing
- Unit test: `detect_revert('Revert "Add auth middleware"', 'This reverts commit abc123')` returns `(True, None)`
- Unit test: `detect_revert('Fix login bug', '')` returns `(False, None)`
- Unit test: PR with `is_revert=True` referencing PR #42 correctly increments `prs_reverted` for PR #42's author
