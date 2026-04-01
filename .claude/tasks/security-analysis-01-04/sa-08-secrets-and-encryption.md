# SA-08: Secrets Management and Token Lifecycle

**Priority:** Planned
**Severity:** MEDIUM (#13), LOW (#19, #20)
**Effort:** Medium
**Status:** Completed

## Findings

### Finding #13: Slack Bot Token Stored in Plaintext
- **File:** `backend/app/models/models.py:664`, `backend/app/services/slack.py:56-61`
- `xoxb-` token stored as plain `Text` column in `slack_config`
- `build_config_response()` strips it from API responses (good), but DB access = token exposure
- Combined with Finding #7 (exposed DB port), this is direct credential theft

### Finding #19: `DEVPULSE_INITIAL_ADMIN` is a Permanent Backdoor
- **File:** `backend/app/api/oauth.py:84-87`
- Any new account matching this env var gets admin role on first login — forever
- No mechanism to disable after the initial admin is established
- No audit log of when the initial admin role was granted

### Finding #20: 7-Day Token Lifetime with No Revocation
- **File:** `backend/app/api/auth.py:24`
- No refresh tokens, no logout endpoint, no token blocklist
- Stolen tokens valid for the full 7 days
- Deactivation blocks access (good), but role changes don't (see SA-04)

## Required Changes

### 1. Encrypt Slack bot token at rest (`backend/app/models/models.py`, `backend/app/services/slack.py`)

Option A — Application-level encryption (simpler):
- Add `ENCRYPTION_KEY` to `config.py` (Fernet-compatible 32-byte key)
- Encrypt `bot_token` before writing to DB, decrypt on read
- Use `cryptography.fernet.Fernet` for symmetric encryption
- Store the encrypted value in the existing `bot_token` column
- Migration: encrypt existing plaintext tokens

Option B — Database-level encryption:
- Use PostgreSQL's `pgcrypto` extension
- More transparent but ties to PostgreSQL

### 2. Auto-disable `DEVPULSE_INITIAL_ADMIN` after use (`backend/app/api/oauth.py`)
- After granting the initial admin role, log an audit event:
  ```python
  logger.warning("Initial admin granted", username=github_username, event_type="system.config")
  ```
- Add a check: if any admin already exists in the `developers` table, ignore `DEVPULSE_INITIAL_ADMIN`
  ```python
  if settings.devpulse_initial_admin:
      existing_admin = await db.execute(
          select(Developer).where(Developer.app_role == "admin").limit(1)
      )
      if existing_admin.scalar_one_or_none():
          # Initial admin already set up, ignore env var
          pass
  ```
- Document in `.env.example` that this should be unset after first admin login

### 3. Reduce token lifetime and add logout (`backend/app/api/auth.py`)
- Reduce `TOKEN_EXPIRY` from 7 days to 4 hours
- Add `POST /auth/logout` endpoint that:
  - Adds token `jti` (JWT ID) to a short-lived blocklist (in-memory set or Redis)
  - Frontend calls on logout to invalidate the token
- Add `jti` claim to JWT generation (`str(uuid4())`)
- Check `jti` against blocklist in `get_current_user()`
- The in-memory blocklist only needs to hold entries for `TOKEN_EXPIRY` duration (4 hours)

### 4. Alternative: Add `token_version` to developers table (simpler revocation)
- Add `token_version: int = 1` column to `Developer` model
- Include `token_version` in JWT payload
- Check in `get_current_user()` that the JWT's `token_version` matches the DB value
- Increment `token_version` on role change, deactivation, or explicit logout
- This is simpler than a blocklist and automatically handles role changes

## Impact Analysis

### Will this break anything?

**Fernet encryption — no column change, no new deps.** `cryptography==44.0.3` is already in `requirements.txt`. The encrypted `gAAAAAB...` ciphertext string fits in the existing `Text` column — no `ALTER COLUMN` DDL needed. A data-only migration encrypts existing plaintext tokens. `bot_token` is nullable, so NULL values are left as-is.

**Slack service test breakage — 2 assertions.** `backend/tests/unit/test_slack_service.py:59` asserts `config.bot_token == "xoxb-test-token"` (reads raw ORM field). Line `:132` has the same assertion. Both must be updated to assert the decrypted value or call a `decrypt_token()` helper. `test_slack_api.py` tests only check `bot_token_configured: bool` and are unaffected.

**Initial admin race condition — negligible.** The "admin already exists" check could race with two simultaneous first-logins. However, `github_username` has a UNIQUE constraint — only one insert succeeds, the second gets IntegrityError → 500. Practical risk is negligible for a one-time setup scenario.

**Token lifetime reduction — no breakage.** No test asserts on the `exp` claim value. Frontend stores JWT in `localStorage` and redirects to `/login` on 401 — already handles expiry. The only user-visible impact is more frequent re-authentication (every 4 hours instead of 7 days).

**`token_version` migration — straightforward.** Latest migration is `033_add_notification_center.py`. Next would be `034_add_token_version.py`: `ALTER TABLE developers ADD COLUMN token_version INTEGER NOT NULL DEFAULT 1`. Only `PATCH /developers/{id}` (the sole write path for `app_role`) needs to increment `token_version` on role change.

### Recommended approach: `token_version` over jti blocklist

The `token_version` approach is simpler, has no runtime storage requirement, and automatically handles role changes (SA-04 synergy). The jti blocklist requires either in-memory state (lost on restart) or Redis. **Prefer `token_version`.**

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/app/services/slack.py` (8 call sites) | Encrypt on write, decrypt on read | Medium — touches all token usage |
| `backend/app/models/models.py:664` | No change (same Text column) | None |
| `backend/migrations/versions/034_*.py` | Data migration: encrypt existing tokens + add `token_version` | Low |
| `backend/app/config.py` | Add `encryption_key: str = ""` + startup validation | Low |
| `backend/app/api/oauth.py:84-87` | Add "admin exists" check before granting initial admin | Low |
| `backend/app/api/auth.py:24` | Reduce `TOKEN_EXPIRY` to 4 hours | Low |
| `backend/app/api/auth.py:36-43` | Include `token_version` in JWT, validate on decode | Low |
| `backend/app/api/developers.py` | Increment `token_version` on `app_role` change | Low |
| `backend/tests/unit/test_slack_service.py:59,132` | Update to assert decrypted value | Required |
| `.env.example` | Add `ENCRYPTION_KEY` with generation hint | Documentation |

## Deliverables

- [x] Encrypt Slack bot token at rest using Fernet symmetric encryption
- [x] Add `ENCRYPTION_KEY` env var to config with startup validation
- [x] Encrypt on write in `update_slack_config()`, decrypt on read at all call sites
- [x] Auto-disable `DEVPULSE_INITIAL_ADMIN` after first admin exists
- [x] Audit log when initial admin is granted or skipped
- [x] Reduce JWT token lifetime from 7 days to 4 hours
- [x] Add `token_version` column to `Developer` model
- [x] Include `token_version` in JWT payload, validate in `get_current_user()`
- [x] Increment `token_version` on role change, deactivation, and soft-delete
- [x] Alembic migration 034 (token_version column + encrypt existing tokens)
- [x] All 852 tests passing

**Approach chosen:** `token_version` over jti blocklist (as recommended in spec). Simpler, no runtime storage, automatic role-change synergy.

## Testing

- [x] Slack bot token encrypted in DB, decrypted correctly on read (`test_slack_service.py::TestUpdateSlackConfig::test_partial_update`)
- [x] NULL bot_token stays NULL (`test_slack_service.py::TestTokenEncryption::test_null_token_returns_none`)
- [x] Invalid ciphertext handled gracefully (`test_slack_service.py::TestTokenEncryption::test_decrypt_invalid_ciphertext_returns_none`)
- [x] `DEVPULSE_INITIAL_ADMIN` ignored when admin exists (`test_oauth.py::TestInitialAdminAutoDisable::test_initial_admin_ignored_when_admin_exists`)
- [x] `token_version` mismatch rejects token with 401 (`test_auth.py::TestTokenVersion::test_mismatched_token_version_returns_401`)
- [x] Matching `token_version` succeeds (`test_auth.py::TestTokenVersion::test_matching_token_version_succeeds`)
- [x] Role change increments `token_version` (`test_auth.py::TestTokenVersion::test_role_change_increments_token_version`)
- [x] Deactivation increments `token_version` (`test_auth.py::TestTokenVersion::test_deactivation_increments_token_version`)
- [x] Existing initial admin test still passes (admin count is 0 at test start)

## Files Modified

| File | Change |
|------|--------|
| `backend/app/config.py` | Added `encryption_key: str` setting |
| `backend/app/services/slack.py` | Added `encrypt_token()`, `decrypt_token()`, `get_decrypted_bot_token()`. Encrypt on write, decrypt on read at all 8 call sites. Changed `_send_dm_to_developer` and `_check_slack_enabled` to pass decrypted token. |
| `backend/app/api/oauth.py` | Added admin-exists check before granting initial admin. Added structlog audit logging. |
| `backend/app/api/auth.py` | Reduced expiry to 4 hours. Added `token_version` to JWT payload and validation in `get_current_user()`. |
| `backend/app/api/developers.py` | Increment `token_version` on `app_role` change, `is_active` toggle, and soft-delete. |
| `backend/app/models/models.py` | Added `token_version` column to `Developer`. |
| `backend/app/schemas/schemas.py` | Added `token_version` to `DeveloperResponse`. |
| `backend/conftest.py` | Added `ENCRYPTION_KEY` test env var. |
| `backend/tests/unit/test_slack_service.py` | Updated encryption assertions. Added `TestTokenEncryption` class (3 tests). |
| `backend/tests/integration/test_auth.py` | Added `TestTokenVersion` class (4 tests). |
| `backend/tests/integration/test_oauth.py` | Added `TestInitialAdminAutoDisable` class (1 test). |
| `.env.example` | Added `ENCRYPTION_KEY` with generation hint. Updated `DEVPULSE_INITIAL_ADMIN` comment. |

## Files Created

| File | Purpose |
|------|---------|
| `backend/migrations/versions/034_add_token_version_and_encrypt_slack_token.py` | Adds `token_version` column, encrypts existing plaintext Slack bot tokens |
