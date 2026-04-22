# Phase 2: OAuth allowlist gating

**Status:** ✅ Completed
**Completed:** 2026-04-22
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** small
**Parent:** installation-scoped-sync/00-overview.md
**Dependencies:** installation-scoped-sync/01-installation-scoped-discovery.md

## Scope

Replace the org-membership OAuth check with a `DEVPULSE_ALLOWED_USERS` allowlist. Comma-separated GitHub usernames that are permitted to sign in. Required in any deployment that has `GITHUB_ORG` unset (otherwise anyone with a GitHub account could sign in).

## Files touched

- `backend/app/api/oauth.py` — replace the `/orgs/{org}/members/{user}` check (line ~100-113)
- `backend/app/config.py` — add `devpulse_allowed_users: str = ""` setting
- `.env.example` — document the new var
- `backend/app/libs/errors.py` — if the 403 should be a `user_permission` category (already the default for HTTPException 403, confirm no special handling needed)

## Checklist

- [ ] `config.py`: add `devpulse_allowed_users: str = ""` and a helper `allowed_users_list -> list[str]` that splits on comma, strips whitespace, lowercases
- [ ] `oauth.py`: replace the `if settings.github_org:` block with:
  - If both `devpulse_allowed_users` and `github_org` are unset → deny all with a config error (fail closed)
  - If `devpulse_allowed_users` is set → check `github_username.lower()` is in the list, 403 if not
  - If only `github_org` is set (legacy) → preserve existing org-member check for back-compat
- [ ] Error message: `f"Access denied: {github_username} is not in DEVPULSE_ALLOWED_USERS"` — mirrors existing org-denied message style
- [ ] `.env.example`: add `DEVPULSE_ALLOWED_USERS=` with a comment explaining it's comma-separated GitHub usernames, case-insensitive
- [ ] Existing `DEVPULSE_INITIAL_ADMIN` behavior is unchanged — first matching user still gets `admin` role on first sign-in

## Testing

- [ ] Sign in with a username in the allowlist → success, Developer record created, JWT returned
- [ ] Sign in with a username NOT in the allowlist → 403 with the expected message
- [ ] `DEVPULSE_INITIAL_ADMIN=anders-vedal` + `DEVPULSE_ALLOWED_USERS=anders-vedal` → first sign-in gets `admin` role
- [ ] Unset both → startup (or first sign-in) fails closed

## Risks

- Fail-open if the check is bypassed: the new logic must default to deny, not allow. Ensure both-unset case returns 403.
- Case sensitivity: GitHub usernames are case-insensitive on login but returned in their canonical casing. Compare lowercased on both sides.
