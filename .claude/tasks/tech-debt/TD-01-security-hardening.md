# TD-01: Security Hardening (Quick Wins)

## Status: TODO
## Priority: HIGH
## Effort: Low (< 2 hours total)

## Summary

Fix three security gaps discovered in the tech debt scan. All are low-effort, high-impact hardening changes.

## Tasks

### 1. Webhook HMAC bypass on empty secret
**File:** `backend/app/api/webhooks.py:29-35`
**Issue:** `github_webhook_secret` defaults to `""` in `config.py`. `verify_signature()` calls `hmac.new(b"", ...)` which produces a deterministic digest — any caller who knows the secret is empty can forge matching `X-Hub-Signature-256` headers and inject arbitrary webhook events.
**Fix:**
- Add an early-exit guard in the webhook endpoint that returns 500/503 if `settings.github_webhook_secret` is empty/unset
- Alternatively, fail app startup if the secret is blank (stricter)
- Add a test confirming requests are rejected when the secret is unconfigured

### 2. JWT secret empty-string default
**File:** `backend/app/config.py:24, 50-51`
**Issue:** If `JWT_SECRET` is unset, the app starts and issues tokens signed with `""`. Any party can forge valid JWTs. A warning is logged but startup is not blocked.
**Fix:**
- Raise a startup error (or at minimum, generate a random secret per-process with a loud warning) when `JWT_SECRET` is empty
- Add validation in `config.py` using pydantic-settings validator
- Add a test confirming token validation fails when secret is empty

### 3. Log ingestion context injection
**File:** `backend/app/api/logs.py:26`
**Issue:** `POST /logs/ingest` spreads `entry.context` — an arbitrary client-controlled `dict[str, Any]` — directly into structlog keyword arguments (`**(entry.context or {})`). A malicious caller can inject arbitrary keys into log records, potentially overwriting reserved fields (`event`, `level`, `timestamp`, `request_id`).
**Fix:**
- Define an allowlist of permitted context keys (e.g., `component`, `url`, `user_agent`, `stack`)
- Filter `entry.context` to only include allowed keys before spreading
- Add `max_length` constraints to `FrontendLogEntry.message` and context values in the Pydantic schema
- Add a test confirming reserved keys are stripped

### 4. CORS tightening (optional, low priority)
**File:** `backend/app/main.py:299-301`
**Issue:** `allow_methods=["*"]` and `allow_headers=["*"]` with `allow_credentials=True` is broader than needed.
**Fix:**
- Replace `allow_methods=["*"]` with explicit list: `["GET", "POST", "PATCH", "DELETE", "OPTIONS"]`
- Replace `allow_headers=["*"]` with explicit list: `["Authorization", "Content-Type"]`

## Acceptance Criteria

- [ ] Webhook endpoint rejects requests when `github_webhook_secret` is empty
- [ ] App startup fails or generates random secret when `JWT_SECRET` is unset
- [ ] Log ingestion filters context keys to an allowlist
- [ ] Tests added for all three fixes
- [ ] Existing tests still pass
