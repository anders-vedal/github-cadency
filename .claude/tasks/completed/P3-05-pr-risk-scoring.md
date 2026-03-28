# Task P3-05: PR Risk Scoring

## Phase
Phase 3 — Make It Proactive

## Status
done

## Blocked By
- P2-05-pr-metadata-capture
- P2-02-review-round-trips

## Blocks
None

## Description
Automatically score open PRs by risk level to help team leads and reviewers prioritize review effort. High-risk PRs (large changes, junior authors, fast-tracked merges) deserve more thorough review. Currently, all PRs are treated equally with no risk signal.

## Deliverables

- [x] `backend/app/services/risk.py` — Pure `compute_pr_risk()` scoring function + async orchestrators (`get_pr_risk`, `get_risk_summary`)
- [x] `backend/app/schemas/schemas.py` — `RiskFactor`, `RiskAssessment`, `RiskSummaryResponse` Pydantic models
- [x] `backend/app/api/stats.py` — `GET /api/stats/pr/{id}/risk` + `GET /api/stats/risk-summary` routes with `Literal` validation
- [x] `frontend/src/utils/types.ts` — TS interfaces + shared `riskLevelStyles`/`riskLevelLabels` constants
- [x] `frontend/src/hooks/useStats.ts` — `useRiskSummary()` hook
- [x] `frontend/src/components/StalePRsSection.tsx` — Optional risk badge column via `riskScores` prop
- [x] `frontend/src/pages/Dashboard.tsx` — "High-Risk PRs" section + risk badges on stale PRs
- [x] `backend/tests/unit/test_risk_scoring.py` — 36 unit tests covering all factors, boundaries, edge cases

### Risk factors (all 10 implemented as specified)

| Factor | Condition | Weight |
|--------|-----------|--------|
| Large PR | additions > 500 | +0.20 |
| Very large PR | additions > 1000 | +0.35 (combined) |
| Many files | changed_files > 15 | +0.10 |
| New contributor | author has < 5 merged PRs in this repo | +0.15 |
| No review | is_merged and no APPROVED review | +0.25 |
| Rubber-stamp only | all reviews are rubber_stamp tier | +0.20 |
| Fast-tracked | time_to_merge_s < 7200 (2 hours) | +0.15 |
| Self-merged | is_self_merged = True | +0.10 |
| High review rounds | review_round_count >= 3 | +0.10 |
| Hotfix branch | head_branch starts with "hotfix/" or "fix/" | +0.10 |

Risk score = min(1.0, sum of applicable weights)
Risk level: low (0-0.3), medium (0.3-0.6), high (0.6-0.8), critical (0.8-1.0)

## Deviations from Original Spec

- **`compute_pr_risk` is a pure function** (not async) — takes a PR ORM object and pre-computed author count. Async orchestrators (`get_pr_risk`, `get_risk_summary`) handle DB access. This makes the scoring logic fully testable without a DB.
- **"Very large PR" weight is 0.35 (not 0.15 additional)** — spec said +0.15 additional on top of +0.20. Implementation uses a single 0.35 weight for >1000 additions (mutually exclusive with the 0.20 large_pr factor) to avoid double-counting.
- **`RiskSummaryResponse` replaces `TeamRiskSummary`** — adds `total_scored` and `prs_by_level` fields; replaces `prs_merged_high_risk` with the more flexible `prs_by_level` dict.
- **`RiskAssessment` includes extra fields** — `number`, `title`, `html_url`, `repo_name`, `author_name`, `author_id`, `is_open` for frontend rendering without extra lookups.
- **`scope` query param added** — `GET /api/stats/risk-summary` accepts `scope=all|open|merged` for flexible filtering (not in original spec).
- **`Literal` validation on API params** — `min_risk_level` and `scope` use `typing.Literal` for automatic 422 on invalid values.
- **`is_merged` checked with `is True`** — handles nullable bool correctly (not just truthiness).
- **Bulk queries** — author merged counts and names fetched in batch to avoid N+1.

## Files Created

| File | Purpose |
|------|---------|
| `backend/app/services/risk.py` | Risk scoring service |
| `backend/tests/unit/test_risk_scoring.py` | 36 unit tests |

## Files Modified

| File | Change |
|------|--------|
| `backend/app/schemas/schemas.py` | Added `RiskFactor`, `RiskAssessment`, `RiskSummaryResponse` |
| `backend/app/api/stats.py` | Added 2 risk routes, `Literal` import, risk service import |
| `frontend/src/utils/types.ts` | Added TS interfaces + shared risk style constants |
| `frontend/src/hooks/useStats.ts` | Added `useRiskSummary()` hook |
| `frontend/src/components/StalePRsSection.tsx` | Optional `riskScores` prop, risk badge column |
| `frontend/src/pages/Dashboard.tsx` | `HighRiskPRsSection` component, risk badge integration |
| `CLAUDE.md` | Backend layout, API table, patterns, completed tasks |
