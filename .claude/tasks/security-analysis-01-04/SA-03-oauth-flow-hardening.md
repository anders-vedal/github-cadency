# SA-03: Harden OAuth Flow

**Priority:** This week
**Severity:** HIGH
**Effort:** Medium
**Status:** Pending

## Findings

### Finding #4: OAuth Missing `state` Parameter — CSRF
- **File:** `backend/app/api/oauth.py:23-30` (login), `backend/app/api/oauth.py:33-116` (callback)
- No `state` nonce generated or verified
- Attacker can CSRF the login flow to bind their GitHub account to a victim's session

### Finding #5: JWT Delivered in URL Query Parameter
- **File:** `backend/app/api/oauth.py:113-116`
- Token appears in redirect as `?token={jwt}` — leaks via browser history, server logs, referrer headers
- 7-day token lifetime amplifies the exposure window

### Finding #8: OAuth Auto-Creates Accounts for Any GitHub User
- **File:** `backend/app/api/oauth.py:76-100`
- Any GitHub user who authenticates gets a `developer` account with `is_active=True`
- No org membership check, no allowlist, no admin approval

## Required Changes

### 1. Add OAuth `state` parameter (`backend/app/api/oauth.py`)
- In `GET /auth/login`:
  - Generate a cryptographically random state nonce (`secrets.token_urlsafe(32)`)
  - Store it in a short-lived HTTP-only cookie (e.g., `devpulse_oauth_state`, 10-min expiry, `SameSite=Lax`)
  - Include `state` in the GitHub authorization URL
- In `GET /auth/callback`:
  - Read the `state` from the query parameter and from the cookie
  - Reject with 400 if they don't match or the cookie is missing
  - Clear the cookie after validation

### 2. Use URL fragment instead of query parameter (`backend/app/api/oauth.py`)
- Change the redirect to use a fragment:
  ```python
  return RedirectResponse(url=f"{settings.frontend_url}/auth/callback#token={token}")
  ```
- Fragments are never sent to servers or included in referrer headers
- Update `frontend/src/pages/AuthCallback.tsx` to read from `window.location.hash` instead of URL search params

### 3. Add org membership check (`backend/app/api/oauth.py`)
- After fetching the GitHub user profile, check org membership:
  ```python
  org_resp = await client.get(
      f"https://api.github.com/orgs/{settings.github_org}/members/{github_username}",
      headers=headers
  )
  if org_resp.status_code == 404:
      # Not an org member — reject
  ```
- Add `GITHUB_ORG` to `config.py` (optional — if unset, skip the check for backward compatibility)
- Return a user-friendly error page/redirect explaining the user is not in the org

### 4. Update frontend auth callback (`frontend/src/pages/AuthCallback.tsx`)
- Parse token from URL fragment instead of query parameter
- Clear the fragment from the URL after extraction (`history.replaceState`)

## Impact Analysis

### Will this break anything?

**Frontend — one file change.** `frontend/src/pages/AuthCallback.tsx:5` uses `useSearchParams` and `searchParams.get('token')` at line 9. Must switch to `window.location.hash` parsing + `history.replaceState` to scrub the fragment. No other frontend files are affected — `frontend/src/utils/api.ts` token storage (`localStorage`) stays the same.

**Backend tests — ALL 3 OAuth tests break:**
- `test_callback_creates_new_developer` (line 43): asserts `"token=" in location` — fails with fragment
- `test_callback_initial_admin_gets_admin_role` (line 57): parses token via `location.split("token=")[1]` — fails; also has no state cookie, so state validation rejects with 400
- `test_callback_existing_user_updates_avatar` (line 87): same `"token=" in location` assertion

All three tests need: (1) pre-seed a state nonce in mock request cookies, (2) update token parsing to handle fragment in redirect URL.

**CORS — no change needed.** `main.py` already has `allow_credentials=True`. The state cookie (`HttpOnly`, `SameSite=Lax`) is set by the backend redirect, which the browser follows natively — no CORS fetch involved.

**`github_org` config — already exists.** `config.py:17` has `github_org: str = ""`. No new config field needed. When empty, skip the org check (backward compatible).

**Latency impact — minimal.** Org membership check adds one GitHub API call (`GET /orgs/{org}/members/{username}`) during the existing `httpx.AsyncClient` block. ~100-300ms, one-time on login.

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/app/api/oauth.py:23-30` | Generate state nonce, set cookie, include in GitHub URL | Medium — new auth flow logic |
| `backend/app/api/oauth.py:33-50` | Validate state from query param + cookie, clear cookie | Medium |
| `backend/app/api/oauth.py:76-100` | Add org membership check (gated on `github_org` non-empty) | Low |
| `backend/app/api/oauth.py:113-116` | Change `?token=` to `#token=` in redirect URL | Low |
| `frontend/src/pages/AuthCallback.tsx:5-15` | Read from `window.location.hash` instead of `useSearchParams` | Low |
| `backend/tests/integration/test_oauth.py` | All 3 tests: add state cookie setup, update token assertion | Required |

### Edge cases

- The `RedirectResponse` status code stays 302 — fragments survive redirects in browsers.
- `history.replaceState` in the frontend clears the token from the address bar before any referrer leak.
- If `github_org` is empty, the org check is skipped entirely — no regression for existing deployments.

## Testing

- Test: OAuth login generates state cookie and includes state in GitHub URL
- Test: Callback rejects mismatched or missing state (400)
- Test: Callback rejects missing state cookie (400)
- Test: Token delivered via fragment, not query parameter
- Test: Non-org member gets rejected at callback (when `GITHUB_ORG` is configured)
- Test: Org check skipped when `GITHUB_ORG` is empty
- Test: Existing org members can still log in normally
- Test: Frontend correctly reads token from URL fragment
