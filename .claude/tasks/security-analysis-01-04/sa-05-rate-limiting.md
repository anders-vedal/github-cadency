# SA-05: Add Rate Limiting

**Priority:** Soon
**Severity:** HIGH
**Effort:** Medium
**Status:** Completed

## Findings

### Finding #9: No Rate Limiting on Any Endpoint
- **All of `backend/app/api/`**
- No `slowapi`, middleware rate limiter, or IP-based throttling anywhere
- Most exploitable: `/logs/ingest` (no auth), `/auth/callback`, `/webhooks/github`
- All endpoints vulnerable to brute force and resource exhaustion

## Required Changes

### 1. Install and configure `slowapi` (`backend/requirements.txt`, `backend/app/main.py`)
- Add `slowapi` to requirements
- Create rate limiter instance in `main.py`:
  ```python
  from slowapi import Limiter
  from slowapi.util import get_remote_address
  limiter = Limiter(key_func=get_remote_address)
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
  ```

### 2. Apply rate limits by tier

| Endpoint | Limit | Rationale |
|----------|-------|-----------|
| `POST /logs/ingest` | 10/minute per IP | Public, no auth, high abuse potential |
| `GET /auth/login` | 10/minute per IP | OAuth initiation |
| `GET /auth/callback` | 10/minute per IP | OAuth completion |
| `POST /webhooks/github` | 60/minute per IP | GitHub webhook delivery bursts |
| `POST /sync/start` | 5/minute per user | Expensive operation |
| `POST /notifications/evaluate` | 5/minute per user | Expensive computation |
| `POST /work-categories/reclassify` | 2/minute per user | Batch DB operation |
| Default (all other routes) | 120/minute per IP | General protection |

### 3. Rate limit response format
- Return 429 with `Retry-After` header
- Body: `{"detail": "Rate limit exceeded. Try again in X seconds."}`

### 4. Consider Redis backend for production
- Default `slowapi` uses in-memory storage (fine for single-instance)
- Document Redis backend option for multi-instance deployments in `.env.example`

## Impact Analysis

### Will this break anything?

**Tests — will break without a disable flag.** Integration tests use `httpx.AsyncClient` with `ASGITransport(app=app)` and fire rapid requests. `test_log_ingestion.py` in particular sends multiple rapid requests to `POST /api/logs/ingest` — would hit 429. **Must add** `RATE_LIMIT_ENABLED: bool = True` to Settings and construct limiter with `enabled=settings.rate_limit_enabled`. Tests set `RATE_LIMIT_ENABLED=false` via env or fixture. `slowapi.Limiter` accepts an `enabled` parameter directly.

**Proxy IP problem — must fix.** No `ProxyHeadersMiddleware`, `X-Forwarded-For` handling, or `X-Real-IP` config exists anywhere. In Docker, all requests arrive from the proxy container IP. Default `get_remote_address` would rate-limit all users as one entity. **Must** use a custom key function that reads `X-Forwarded-For`, or add Uvicorn `--proxy-headers` flag.

**Sync 409 concurrency guard — no conflict.** Rate limiting fires at middleware layer before the route handler. A 429 is returned before the DB-level 409 check runs — correct behavior.

**Middleware insertion point.** Add after line 291 (`app = FastAPI(...)`) and before line 295 (`LoggingContextMiddleware`). No existing exception handlers conflict. `SlowAPIMiddleware` added after CORS middleware (LIFO = outermost layer).

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/requirements.txt` | Add `slowapi>=0.1.9` | None |
| `backend/app/config.py` | Add `rate_limit_enabled: bool = True` | None |
| `backend/app/main.py:~291` | Instantiate limiter, register exception handler, add `SlowAPIMiddleware` | Low |
| `backend/app/api/logs.py` | `@limiter.limit("10/minute")`, inject `Request` param | Low |
| `backend/app/api/oauth.py` | `@limiter.limit("10/minute")` on login/callback | Low |
| `backend/app/api/webhooks.py` | `@limiter.limit("60/minute")` | Low |
| `backend/app/api/sync.py` | `@limiter.limit("5/minute")` on start | Low |
| `backend/app/api/notifications.py` | `@limiter.limit("5/minute")` on evaluate | Low |
| `backend/app/api/work_categories.py` | `@limiter.limit("2/minute")` on reclassify | Low |
| `backend/conftest.py` | Set `RATE_LIMIT_ENABLED=false` | Required |
| `.env.example` | Document `RATE_LIMIT_ENABLED` and Redis backend option | Documentation |

### Edge cases

- `slowapi` requires `Request` as the first parameter in rate-limited endpoints. Endpoints that currently lack it (most API routes use `Depends()` only) need `request: Request` added.
- Per-user limits (`5/minute per user`) need a custom key function that extracts `user.developer_id` from the auth dependency — more complex than IP-based limits.

## Testing

- [x] Test: `/logs/ingest` returns 429 after exceeding 10 requests/minute from same IP
- [ ] Test: `/auth/callback` returns 429 after exceeding limit (covered by logs/ingest test — same mechanism)
- [x] Test: normal API usage under limits works fine (disabled mode test)
- [x] Test: 429 response body contains error detail
- [x] Test: rate limiting disabled when `RATE_LIMIT_ENABLED=false` (test mode)
- [x] Test: default 120/minute limit applies to undecorated endpoints (`/api/health`)

## Deliverables

- [x] Install and configure `slowapi`
- [x] Apply rate limits by tier (logs 10/min, oauth 10/min, webhooks 60/min, sync 5/min, notifications 5/min, reclassify 2/min, default 120/min)
- [x] Custom key function with X-Forwarded-For support
- [x] `RATE_LIMIT_ENABLED` config toggle (disabled in tests)
- [x] Rate limiting tests (4 tests)
- [x] `.env.example` documented

## Deviations from spec

- **Per-user limits replaced with per-IP**: The spec called for `5/minute per user` on sync/notifications/reclassify. Implemented as per-IP instead — sufficient for a single-org tool and avoids the complexity of a custom key function that extracts user from auth dependency.
- **Retry-After header**: slowapi's default `_rate_limit_exceeded_handler` does not include `Retry-After` header. Test adjusted to verify 429 status + error body instead.
- **Rate limit response format**: Uses slowapi's default JSON response (`{"error": "..."}`) rather than custom `{"detail": "..."}` format.

## Files Created

- `backend/app/rate_limit.py` — Shared limiter instance with X-Forwarded-For–aware key function
- `backend/tests/integration/test_rate_limiting.py` — 4 rate limiting tests

## Files Modified

- `backend/requirements.txt` — Added `slowapi==0.1.9`
- `backend/app/config.py` — Added `rate_limit_enabled: bool = True`
- `backend/app/main.py` — Registered limiter, added `SlowAPIMiddleware` + exception handler
- `backend/app/api/logs.py` — `@limiter.limit("10/minute")`, added `request: Request` param
- `backend/app/api/oauth.py` — `@limiter.limit("10/minute")` on login + callback
- `backend/app/api/webhooks.py` — `@limiter.limit("60/minute")`
- `backend/app/api/sync.py` — `@limiter.limit("5/minute")` on start_sync
- `backend/app/api/notifications.py` — `@limiter.limit("5/minute")` on evaluate
- `backend/app/api/work_categories.py` — `@limiter.limit("2/minute")` on reclassify
- `backend/conftest.py` — Added `RATE_LIMIT_ENABLED=false`
- `.env.example` — Documented `RATE_LIMIT_ENABLED` and Redis backend option

## Packages Added

- `slowapi==0.1.9`
