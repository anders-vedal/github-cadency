# SA-01: Enforce Non-Empty Secrets at Startup

**Priority:** Immediate
**Severity:** CRITICAL
**Effort:** Low
**Status:** Pending

## Findings

### Finding #1: JWT Secret Defaults to Empty String
- **File:** `backend/app/config.py:24`, `backend/app/api/auth.py:27,37`
- PyJWT signs/verifies with `""` as a valid HS256 key
- Attacker can forge `{"developer_id": 1, "app_role": "admin"}` tokens
- Startup only emits `logger.warning` — no abort

### Finding #2: Webhook Secret Defaults to Empty String
- **File:** `backend/app/api/webhooks.py:29-35`, `backend/app/config.py:16`
- `HMAC(b"", payload)` is deterministic — attacker can compute valid signatures
- No preflight check warns about missing webhook secret
- Allows injection of arbitrary PR/review/issue data into the database

## Required Changes

### 1. Startup validation for JWT secret (`backend/app/config.py`)
- In the existing startup validation (around line 50), replace the `logger.warning` with a `SystemExit` or `RuntimeError` if `jwt_secret` is empty or shorter than 32 characters
- Example:
  ```python
  if not settings.jwt_secret or len(settings.jwt_secret) < 32:
      raise SystemExit("FATAL: JWT_SECRET must be set and at least 32 characters")
  ```

### 2. Startup validation for webhook secret (`backend/app/config.py`)
- Add `github_webhook_secret` to `validate_github_config()` (currently only checks app ID, installation ID, key path)
- Log a warning if empty (webhook processing is optional, so don't block startup)

### 3. Reject webhooks when secret is unset (`backend/app/api/webhooks.py`)
- At the top of the webhook handler, check `if not settings.github_webhook_secret` and return 501 ("Webhook signature verification not configured")
- This is the runtime safety net in case the startup check is bypassed

### 4. Update `.env.example`
- Add comments emphasizing these secrets MUST be set
- Provide a generation command: `openssl rand -hex 32`

## Impact Analysis

### Will this break anything?

**Tests — one fixture must change.** `backend/conftest.py:11` sets `JWT_SECRET` to `"test-jwt-secret-for-testing"` (26 chars). If we enforce >=32 chars, this fails. Fix: lengthen to `"test-jwt-secret-for-testing-only"` (32 chars). Same fallback in `backend/tests/integration/test_oauth.py:78` must match. The webhook secret `"test-webhook-secret"` (20 chars) is fine — webhook secret only needs non-empty check, no length minimum (HMAC keys have no minimum for correctness).

**Docker startup — intentionally breaks on bad config.** The `SystemExit` fires at module-import time (`config.py:50`), before `lifespan()` runs. Uvicorn catches `SystemExit` and terminates cleanly. A misconfigured container will restart-loop, which is the correct behavior — it should not silently serve with an empty secret.

**No other callers.** `settings.jwt_secret` is only used in `auth.py` (encode/decode). `settings.github_webhook_secret` is only used in `webhooks.py` (HMAC).

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/app/config.py:50-51` | `SystemExit` if `jwt_secret` empty or <32 chars | Intentional — blocks misconfigured startup |
| `backend/app/config.py:~158` | Add webhook secret presence to `validate_github_config()` as `warn` status | None |
| `backend/app/api/webhooks.py:~44` | Return 501 if `github_webhook_secret` is empty | None |
| `backend/conftest.py:11` | Lengthen test JWT secret to 32+ chars | Required for tests to pass |
| `backend/tests/integration/test_oauth.py:78` | Match the longer fallback string | Required for tests to pass |
| `.env.example:8,16` | Add `openssl rand -hex 32` generation hint | Documentation only |

### Edge cases

- The `SystemExit` placement at module level (config.py:50) is correct — it fires on `import app.config`, before any route or lifespan code. Do NOT move it into `validate_github_config()`, which is called lazily.
- `validate_github_config()` returns structured check results for the frontend config page — adding webhook secret as a `warn` check fits the existing pattern.
- Changes are independent: config.py first, then webhooks.py, then test fixtures. No ordering dependency between the two secret checks.

## Testing

- Unit test: app refuses to start with empty `JWT_SECRET`
- Unit test: app refuses to start with `JWT_SECRET` shorter than 32 chars
- Unit test: webhook endpoint returns 501 when `GITHUB_WEBHOOK_SECRET` is empty
- Unit test: webhook rejects requests with invalid HMAC when secret is set
- Integration: verify existing JWT flow still works with a proper secret
