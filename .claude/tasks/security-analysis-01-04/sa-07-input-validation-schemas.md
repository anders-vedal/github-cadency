# SA-07: Input Validation — ReDoS Protection and Schema Length Limits

**Priority:** Planned
**Severity:** HIGH (ReDoS), MEDIUM (length limits)
**Effort:** Medium
**Status:** Completed

## Findings

### Finding #12: ReDoS via Admin-Supplied Regex Rules
- **File:** `backend/app/services/work_categories.py:100-110, 236-240`
- Admin-created `title_regex` rules only checked for compilation, not catastrophic backtracking
- Patterns like `(a+)+$` cause exponential backtracking on long PR titles
- `reclassify_all()` runs the regex against every PR/issue — event loop blocked for minutes

### Finding #17: No String Length Limits on Pydantic Fields
- **File:** `backend/app/schemas/schemas.py` — throughout
- No model uses `Field(max_length=...)` anywhere
- Unbounded fields: `display_name`, `notes`, `description`, `title`, `message`, `sync_scope`, etc.
- Enables memory pressure during request parsing and storage abuse

## Required Changes

### 1. ReDoS protection for regex rules (`backend/app/services/work_categories.py`)

Option A — Use `re2` library (preferred):
- Install `google-re2` or `pyre2` which guarantees linear-time matching
- Replace `re.search(pattern, text)` with `re2.search(pattern, text)` in `classify_work_item_with_rules()`

Option B — Timeout wrapper:
- Run regex matching in a thread with a timeout:
  ```python
  import concurrent.futures
  def safe_regex_match(pattern: str, text: str, timeout: float = 0.1) -> bool:
      with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
          future = executor.submit(re.search, pattern, text)
          try:
              return future.result(timeout=timeout) is not None
          except concurrent.futures.TimeoutError:
              return False
  ```

Option C — Pattern complexity validation:
- Reject patterns with nested quantifiers at creation time:
  ```python
  DANGEROUS_PATTERNS = re.compile(r'(\([^)]*[+*][^)]*\))[+*]')
  if DANGEROUS_PATTERNS.search(pattern):
      raise ValueError("Pattern contains nested quantifiers which may cause performance issues")
  ```

### 2. Add `max_length` to critical Pydantic fields (`backend/app/schemas/schemas.py`)

Priority fields (most exposed or user-facing):

| Schema | Field | Suggested max_length |
|--------|-------|---------------------|
| `DeveloperCreate` | `display_name` | 200 |
| `DeveloperCreate` | `email` | 320 |
| `DeveloperCreate` | `team`, `office`, `location` | 200 |
| `DeveloperCreate` | `timezone` | 100 |
| `DeveloperCreate` | `notes` | 5000 |
| `DeveloperCreate` | `skills` (each item) | 100 |
| `GoalCreate` | `title` | 500 |
| `GoalCreate` | `description` | 5000 |
| `WorkCategoryCreate` | `display_name` | 200 |
| `WorkCategoryCreate` | `description` | 2000 |
| `WorkCategoryRuleCreate` | `match_value` | 1000 |
| `WorkCategoryRuleCreate` | `description` | 2000 |
| `SyncTriggerRequest` | `sync_scope` | 500 |
| `FrontendLogEntry` | `message` | 4000 |
| `FrontendLogEntry` | `event_type` | 100 |
| `FrontendLogEntry` | `url` | 2000 |
| `DismissAlertTypeRequest` | `alert_type` | 100 |

### 3. Validate `alert_type` and `severity` against enums
- In `GET /notifications` query params, validate `severity` against `{"critical", "warning", "info"}`
- Validate `alert_type` in `DismissAlertTypeRequest` against the `ALERT_TYPE_META` registry keys

## Impact Analysis

### Will this break anything?

**re2 is NOT compatible with existing regex patterns.** `_MENTION_RE` in `github_sync.py:1008-1009` uses `(?<!\w)` (negative lookbehind) and `(?=[a-zA-Z0-9])` (lookahead) — both unsupported by re2. **Option A (re2) cannot be applied globally.** The safe path is Option C (pattern complexity validation at creation time) targeting only admin-supplied `title_regex` rules, while leaving `_MENTION_RE` and `classify_comment_type()` on stdlib `re`. The hardcoded patterns in `work_category.py:79-82` have no nested quantifiers and are not a ReDoS risk.

**`display_name` max_length 200 is too low.** GitHub allows display names up to 255 chars. A GitHub user with a 255-char display name synced via `resolve_author()` would fail the 200-char limit on `DeveloperCreate`. **Must raise to 255** to match GitHub's ceiling. GitHub usernames are max 39 chars (well within any proposed limit).

**`DeveloperUpdate` needs the same limits as `DeveloperCreate`.** They share the same writable fields — any `max_length` added to Create must also be added to Update.

**No existing data violations.** Default seeded roles/categories use short strings. Test fixtures use `"testuser"`, `"Test User"`, `"admin@example.com"` — all well within limits. No tests use oversized strings.

**`severity`/`alert_type` validation — straightforward.** `GET /notifications` at `notifications.py:39-40` takes raw `str` params. `ALERT_TYPE_META` registry exists in `notifications.py` — validating against its keys is clean. `Literal[...]` or `field_validator` both work.

### Corrected max_length values

| Schema | Field | Original proposal | Corrected | Reason |
|--------|-------|------------------|-----------|--------|
| `DeveloperCreate` | `display_name` | 200 | **255** | GitHub max display name |
| `DeveloperUpdate` | (all matching fields) | (missing) | **Same as Create** | Shared writable fields |

### Recommended ReDoS approach

**Option C (pattern complexity validation)** — reject patterns with nested quantifiers at creation time in `work_categories.py:236-240` and `531-535`. This is the safest: no new dependency, no runtime overhead, and the only code path that runs admin-supplied regex on untrusted data is `classify_work_item_with_rules()`.

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/app/services/work_categories.py:236-240, 531-535` | Add nested-quantifier rejection in regex validation | Low |
| `backend/app/schemas/schemas.py` (throughout) | Add `Field(max_length=...)` to all listed fields | Low |
| `backend/app/api/notifications.py:38-49` | Validate `severity`/`alert_type` against enum/registry | Low |

## Testing

- [x] Test: regex pattern with nested quantifiers is rejected at creation (422)
- [x] Test: valid regex patterns still accepted
- [ ] Test: `reclassify_all()` completes in reasonable time (not added — reclassify uses pre-validated rules only)
- [x] Test: oversized string fields return 422 validation error
- [x] Test: 255-char display_name is accepted
- [x] Test: invalid `severity`/`alert_type` values return 422
- [x] Test: valid inputs at the boundary of max_length are accepted

## Files Modified

- `backend/app/services/work_categories.py` — Added `_validate_regex_safe()` with nested-quantifier detection, replaced inline `re.compile()` in 3 sites
- `backend/app/schemas/schemas.py` — Added `Field(max_length=...)` to `DeveloperCreate`, `DeveloperUpdate`, `GoalCreate`, `GoalSelfCreate`, `WorkCategoryCreate`, `WorkCategoryRuleCreate`, `SyncTriggerRequest`, `DismissAlertTypeRequest`; added `validate_skills` field_validator
- `backend/app/api/notifications.py` — Added `severity`/`alert_type` validation against enums in `list_notifications` and `dismiss_notification_type`
- `backend/tests/unit/test_work_categories.py` — 4 unit tests for `_validate_regex_safe`
- `backend/tests/integration/test_work_categories_api.py` — 4 integration tests (ReDoS rejection, valid regex, oversized fields)
- `backend/tests/integration/test_notifications_api.py` — 5 integration tests (severity/alert_type validation)
- `backend/tests/integration/test_developers_api.py` — 4 integration tests (max_length boundary tests)

## Deviations

- `reclassify_all()` timing test not added: reclassify only runs rules that already passed validation at creation time, so ReDoS-vulnerable patterns can never reach it. The unit tests for `_validate_regex_safe` cover the prevention layer.
- `FrontendLogEntry` already had `max_length` on all fields — no changes needed.
