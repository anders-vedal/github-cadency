# Task P4-03: Review Comment Categorization

## Phase
Phase 4 — Make It Best-in-Class

## Status
done

## Blocked By
- M1-review-quality-signals

## Blocks
None

## Description
Categorize review comments into types (nit, blocker, architectural, question, praise, suggestion, general) to distinguish meaningful review feedback from noise. A PR with 20 nit comments is very different from one with 3 architectural concerns, but the current quality tier treats them identically. Uses keyword/prefix detection on already-stored comment bodies.

## Deliverables

- [x] Database migration — `comment_type` column on `pr_review_comments` (String(30), server_default "general")
- [x] `classify_comment_type(body: str) -> str` — keyword-based classifier in github_sync.py
- [x] Call `classify_comment_type()` in `upsert_review_comment()` during sync
- [x] `comment_type_distribution`, `nit_ratio`, `blocker_catch_rate` in developer stats
- [x] `comment_type_distribution: dict[str, int]`, `nit_ratio: float | None`, `blocker_catch_rate: float | None` added to `DeveloperStatsResponse`
- [x] Review quality integration: blocker comment → minimum "standard" tier; 3+ architectural comments → "thorough" tier
- [x] Unit tests for `classify_comment_type()` (30 tests)
- [x] Unit tests for extended `classify_review_quality()` params (8 tests)
- [x] Integration tests for comment type stats + quality tier promotion (6 tests)

## Deviations from Original Spec

- **Enhanced keyword lists**: Added `style:`, `cosmetic:`, `tiny:`, `bug:`, `must-fix:` prefixes; `security issue`, `race condition`, `data loss`, `will break`, `memory leak` content patterns; GitHub ` ```suggestion` block detection; `have you considered`, `what about`, `alternatively`, `you could also`, `perhaps` for suggestions; broader praise list (`awesome`, `excellent`, `looks good`, `nice catch`, `good call`, `clean code`, `👍`)
- **Priority-based ordering**: Explicit prefixes checked first (nit:/blocker:/suggestion:/question:), then content patterns, then loose fallbacks (ends with `?`, starts with `nice`/`great`). Prevents "nit: why?" from being classified as question.
- **Integrated quality tier approach**: Comment type signals (`has_blocker_comment`, `architectural_comment_count`) are parameters to `classify_review_quality()` rather than post-hoc promotion, keeping all classification logic in one decision tree.
- **Date filter consistency**: Stats queries use `PRReview.submitted_at` (not `PRReviewComment.created_at`) for date filtering, matching peer metrics.

## Files Created
- `backend/migrations/versions/010_add_comment_type.py`
- `backend/tests/unit/test_comment_type.py`
- `backend/tests/integration/test_comment_type_stats.py`

## Files Modified
- `backend/app/models/models.py` — added `comment_type` to `PRReviewComment`
- `backend/app/services/github_sync.py` — added `classify_comment_type()`, extended `classify_review_quality()` with `has_blocker_comment`/`architectural_comment_count` params, updated `upsert_review_comment()` and `recompute_review_quality_tiers()`
- `backend/app/services/stats.py` — added comment type distribution, nit_ratio, blocker_catch_rate queries
- `backend/app/schemas/schemas.py` — added 3 fields to `DeveloperStatsResponse`
- `backend/tests/unit/test_review_quality.py` — added 8 tests for new params
- `CLAUDE.md` — updated design decisions, completed tasks list
