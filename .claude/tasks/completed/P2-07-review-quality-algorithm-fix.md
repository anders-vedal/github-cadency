# Task P2-07: Fix Review Quality Classification Algorithm

## Phase
Phase 2 — Make It Smart

## Status
completed

## Blocked By
- M1-review-quality-signals

## Blocks
None

## Description
Rework `classify_review_quality()` to use multiple signals instead of only character count. The current algorithm penalizes concise, precise reviewers and rewards verbose but shallow reviewers. A `CHANGES_REQUESTED` review — the strongest quality signal — is ignored in classification.

## Current Algorithm (github_sync.py:242-261)
```
thorough:     body > 500 chars OR 3+ inline comments
standard:     body 100-500 chars
rubber_stamp: state=APPROVED AND body < 20 chars
minimal:      everything else
```

## New Algorithm
```
thorough:     body > 500 chars, OR 3+ inline comments, OR (CHANGES_REQUESTED AND body > 100 chars)
standard:     body 100-500 chars, OR CHANGES_REQUESTED (any length), OR body contains code blocks (```)
rubber_stamp: state=APPROVED AND body < 20 chars AND 0 inline comments
minimal:      everything else
```

Key changes:
1. `CHANGES_REQUESTED` automatically qualifies as minimum "standard" — blocking a merge is meaningful review work regardless of comment length
2. Code blocks in review body indicate technical substance (code suggestions, examples)
3. `rubber_stamp` now additionally requires 0 inline comments — if there are inline comments, the reviewer did engage with the code

## Deliverables

- [x] **backend/app/services/github_sync.py** — Rewrite `classify_review_quality()` with new multi-signal algorithm (CHANGES_REQUESTED, code blocks, inline comment guard on rubber_stamp)
- [x] **backend/scripts/recompute_review_quality.py** — One-time migration script to recompute `quality_tier` for all existing reviews (`python -m scripts.recompute_review_quality`)
- [x] **frontend/src/components/charts/ReviewQualityDonut.tsx** — Rename "Rubber Stamp" display label to "Quick Approval"

## Testing

- [x] Unit test: `CHANGES_REQUESTED` with empty body → "standard" (was "minimal")
- [x] Unit test: `APPROVED` with 15-char body but 2 inline comments → "minimal" (not "rubber_stamp")
- [x] Unit test: `COMMENTED` with code block in body → "standard"
- [x] Unit test: backward compatibility — existing "thorough" classifications still hold
- [x] Full test suite: 252 tests pass

## Files Modified

- `backend/app/services/github_sync.py` — Rewrote `classify_review_quality()`, updated call sites in `upsert_review()` and `recompute_review_quality_tiers()` to pass `body`
- `frontend/src/components/charts/ReviewQualityDonut.tsx` — "Rubber Stamp" → "Quick Approval" label
- `backend/tests/unit/test_review_quality.py` — 26 tests (8 new, 2 updated for changed behavior)

## Files Created

- `backend/scripts/recompute_review_quality.py` — One-time script to recompute quality tiers for existing data
