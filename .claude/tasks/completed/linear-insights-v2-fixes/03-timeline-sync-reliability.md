# Phase 03: GitHub timeline sync reliability

**Status:** completed
**Priority:** High
**Type:** bugfix
**Apps:** devpulse
**Effort:** small
**Parent:** linear-insights-v2-fixes/00-overview.md

## Blocked By
- None

## Blocks
- 07-missing-test-files

## Description

Phase 09 of the original epic (`github_timeline.py`) integrated timeline fetch into
`sync_repo` but didn't actually enforce the rate-limit back-off it logs, and inlines 17
`itemTypes` per aliased PR block instead of using the fragment that already exists at the top
of the file. On repos with many open PRs, this risks hitting the GraphQL document-size limit
and eventually the point-complexity limit.

## Deliverables

### `backend/app/services/github_timeline.py` — enforce rate-limit back-off

**Bug** (lines 325-334): `_fetch_single_batch` reads
`rateLimit { cost remaining resetAt }` from every GraphQL response and logs it, but no code
path sleeps when `remaining` drops below the 10% threshold. On large repos consecutive
50-PR batches will eventually 403.

**Fix**: mirror the existing pattern in `LinearClient.query()`:

1. Parse `rateLimit.remaining`, `rateLimit.limit` (or the known GitHub cap of 5000), and
   `rateLimit.resetAt` from each response.
2. When `remaining / limit < 0.10`, compute `sleep_seconds = max(0, resetAt - now)` and await
   the sleep before issuing the next batch.
3. Log a warning with the sleep duration so ops can observe it in structlog.
4. On 403 with a rate-limit error class, retry once after the computed sleep. If the retry
   also 403s, propagate the exception (stop the sync cleanly).

Use the existing project structlog convention: `logger.warning("github.rate_limit.backoff",
sleep_s=..., remaining=..., reset_at=...)`.

### `backend/app/services/github_timeline.py` — use GraphQL fragment for batched alias blocks

**Issue** (lines 259-292): the batched query builder inlines all 17 `itemTypes` per alias
block. For a 50-PR batch, the query string is roughly 50 × 600 bytes = ~30 KB per request,
risking the document-size limit on top of point complexity.

**Fix**: Reuse `_TIMELINE_FRAGMENT` (already defined at the top of the file and used by the
non-batched `TIMELINE_QUERY`). Each alias block should reference the fragment instead of
re-listing the type names:

```graphql
pr0: node(id: $id0) {
  ... on PullRequest {
    ...TimelineFields
  }
}
```

Declare the fragment once in the query document via the existing `_TIMELINE_FRAGMENT`
constant; the builder only emits the per-PR alias blocks and the fragment spread reference.

### `backend/app/services/linear_sync.py` — warn on pagination cap hit

**Issue** (`_fetch_all_comment_pages` / `_fetch_all_history_pages`): the `_MAX_INNER_PAGES =
50` cap silently truncates when hit. A pathological 10,000-comment issue would lose data with
no operator signal.

**Fix**: when the loop exits because the page cap was reached (not because `hasNextPage` is
False), emit a structured warning:
```python
logger.warning(
    "linear.pagination.cap_hit",
    issue_external_id=issue_external_id,
    connection="comments",  # or "history"
    max_pages=_MAX_INNER_PAGES,
)
```

Consider raising `_MAX_INNER_PAGES` to 200 if the warning becomes common post-fix; start with
a warning so real-world frequency is observable.

## Testing

- `backend/tests/unit/test_github_timeline_rate_limit.py`: stub a GraphQL response with
  `rateLimit.remaining=100` (of 5000), assert the client sleeps before the next batch.
  Stub a 403-rate-limit response, assert retry after sleep, and a second 403 propagates.
- Extend an existing Linear sync test to stub a `comments.pageInfo.hasNextPage=True` loop
  that returns True for 51 iterations. Assert the cap warning is emitted and sync completes.
- Query-string inspection test: build a batch for 5 PRs, assert the document contains the
  fragment definition once and 5 references, not 5 inline type lists.

## Acceptance criteria

- [x] `_fetch_single_batch` sleeps when `rateLimit.remaining` drops below 10%; on 403 retries
      once then propagates
- [x] Batched timeline queries use a shared `$itemTypes` GraphQL variable (declared once per
      query document) so the 17 enum names aren't inlined per-PR alias block; node
      projections use the existing `_TIMELINE_FRAGMENT`
- [x] `_fetch_all_comment_pages` / `_fetch_all_history_pages` emit a structured warning when
      `_MAX_INNER_PAGES` is exceeded
- [x] Regression tests for all three fixes pass

## Implementation notes

- GraphQL fragments don't apply to argument lists — the cost was the per-alias
  `itemTypes: [...]` enum list, not the node projection. Promoted `$itemTypes:
  [PullRequestTimelineItemsItemType!]!` to a query variable sent as one JSON array; the
  per-alias cost drops from ~30 tokens per block to a single `$itemTypes` reference.
- `_rate_limit_sleep_seconds()` helper reads `rateLimit.remaining / rateLimit.limit`,
  sleeps until `resetAt` when the ratio drops below 10%. On 403 with or without
  `Retry-After`, retries once then propagates.
- `_fetch_all_comment_pages` / `_fetch_all_history_pages` now use a `for...else` block:
  when the loop runs to completion without `break`ing (i.e. the cap was hit while
  `hasNextPage` was still true), emits `linear.pagination.cap_hit` with the connection
  name and `_MAX_INNER_PAGES`.

## Files Modified

- `backend/app/services/github_timeline.py`
- `backend/app/services/linear_sync.py` (pagination cap warnings)
