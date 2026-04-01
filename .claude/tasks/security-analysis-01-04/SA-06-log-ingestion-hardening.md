# SA-06: Harden Log Ingestion Endpoint

**Priority:** Soon
**Severity:** MEDIUM (field injection), HIGH (combined with no rate limiting)
**Effort:** Medium
**Status:** Pending

## Findings

### Finding #10: Arbitrary Field Injection + No Input Bounds
- **File:** `backend/app/api/logs.py:26`, `backend/app/schemas/schemas.py:1518-1526`
- `**(entry.context or {})` spreads unconstrained `dict[str, Any]` into structlog kwargs
- Attacker can override reserved fields (`event_type`, `source`, `request_id`, `level`)
- No length limits on `message`, `event_type`, `url`, or context values
- High-cardinality key injection can DoS Loki (creates new label stream per unique key)
- 50 entries/request * unlimited requests = unbounded log flooding

## Required Changes

### 1. Allowlist context keys (`backend/app/api/logs.py`)
- Define an allowlist of accepted context keys:
  ```python
  ALLOWED_CONTEXT_KEYS = {"component", "action", "page", "user_agent", "stack", "error_name", "error_message"}
  ```
- Filter `entry.context` to only include allowed keys before spreading
- Alternatively, nest the entire `context` under a single `frontend_context` key instead of spreading

### 2. Add field length limits (`backend/app/schemas/schemas.py`)
- On `FrontendLogEntry`:
  ```python
  message: str = Field(max_length=4000)
  level: str = Field(max_length=20)
  event_type: str = Field(max_length=100)
  url: str | None = Field(default=None, max_length=2000)
  context: dict[str, Any] | None = Field(default=None)
  ```
- Add a validator on `context` to limit:
  - Max number of keys (e.g., 20)
  - Max key length (e.g., 50 characters)
  - Max value serialized size (e.g., 1000 characters per value)

### 3. Prevent reserved field override (`backend/app/api/logs.py`)
- Strip reserved structlog fields from context before spreading:
  ```python
  RESERVED_FIELDS = {"event_type", "source", "request_id", "level", "logger", "timestamp"}
  safe_context = {k: v for k, v in (entry.context or {}).items() if k not in RESERVED_FIELDS}
  ```

### 4. Validate `event_type` against allowed values
- Restrict to known frontend event types:
  ```python
  ALLOWED_EVENT_TYPES = {"frontend.error", "frontend.warn", "frontend.info"}
  ```
- Reject or default entries with unknown `event_type`

### 5. Rate limiting (covered by SA-05, but noting dependency)
- This endpoint needs rate limiting from SA-05 (10/minute per IP)

## Impact Analysis

### Will this break anything?

**Allowlist in the task spec is WRONG — would drop all real frontend data.** The proposed allowlist `{"component", "action", "page", "user_agent", "stack", "error_name", "error_message"}` does NOT match what the frontend actually sends. `frontend/src/utils/logger.ts` global error handlers send `{"filename", "lineno", "colno"}` as context keys. No other `logger.error` or `logger.warn` calls exist in any component. The allowlist must be corrected to:
```python
ALLOWED_CONTEXT_KEYS = {"filename", "lineno", "colno", "component", "action", "page", "stack", "error_name", "error_message", "status"}
```
(`component` and `status` are used in test fixtures at `test_log_ingestion.py:54`.)

**Event types — safe.** Frontend only sends `frontend.error` and `frontend.warn`. The proposed `ALLOWED_EVENT_TYPES = {"frontend.error", "frontend.warn", "frontend.info"}` is correct; `frontend.info` is never actually sent but inclusion is harmless.

**Length limits — safe.** Frontend messages are short error strings. `url` is `window.location.href` (well under 2000 chars). No existing frontend code would be rejected.

**Test breakage — depends on strategy.** `backend/tests/integration/test_log_ingestion.py:54` asserts `log["component"] == "Dashboard"` and `log["status"] == 500` as top-level JSON keys (because context is currently spread). If we switch to nesting under `frontend_context` instead of spreading, this test breaks. If we keep spread-with-allowlist, the test passes only if `component` and `status` are in the allowlist.

**Structlog pipeline — no conflict.** The pipeline (`merge_contextvars` → `add_log_level` → `StackInfoRenderer` → `TimeStamper` → `JSONRenderer`) has no processor that reads or transforms arbitrary kwargs keys. Filtering before the spread is clean.

### Corrected allowlist

```python
ALLOWED_CONTEXT_KEYS = {
    # Currently sent by frontend logger.ts
    "filename", "lineno", "colno",
    # Future-proofing for component-level logging
    "component", "action", "page", "stack",
    "error_name", "error_message", "status",
}
```

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/app/api/logs.py:26` | Filter context keys, strip reserved fields | Low |
| `backend/app/schemas/schemas.py:1518-1526` | Add `max_length` to `FrontendLogEntry` fields, add context validator | Low |
| `backend/tests/integration/test_log_ingestion.py` | May need updates depending on spread vs nest strategy | Required |

## Testing

- Test: context keys not in allowlist are stripped (specifically: `filename`, `lineno`, `colno` ARE preserved)
- Test: reserved fields (`event_type`, `source`, `request_id`) in context are stripped
- Test: oversized `message` (>4000 chars) returns 422
- Test: context with >20 keys returns 422
- Test: valid log entries with `filename`/`lineno`/`colno` still processed correctly
- Test: unknown `event_type` is rejected or defaulted
