# Phase 06: Self-serve signup + onboarding

**Status:** Planned
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** large
**Parent:** multi-tenancy/00-overview.md
**Dependencies:** multi-tenancy/02-org-scoped-auth.md, multi-tenancy/04-per-org-quotas.md

## Scope

The public-facing signup flow. A visitor arrives at `devpulse.claros.no`, clicks "Sign up", creates an org, authenticates with GitHub, installs the App into their GitHub organization, selects initial repos, optionally connects Linear, and lands on a "sync in progress" dashboard. All of this must be zero-touch — no operator intervention required.

## What "done" looks like

- `/signup` page is publicly reachable (no auth required)
- End-to-end flow: visitor → GitHub OAuth → create org → install GitHub App → pick repos → (optional) Linear connect → first sync auto-kicks → dashboard shows "syncing..." → first data within ~2 min on a small repo
- Email verification required before signup completes (prevents throwaway-email spam signups)
- Clear errors at every step (GitHub install cancelled, Linear API key invalid, quota would be exceeded on repo selection)
- First admin of the org can invite teammates by email or GitHub login
- An "onboarding checklist" card on the dashboard tracks progress until the org has ≥1 sync completed + ≥1 invited user

## Key design decisions

- **Org-first, install-after**: user creates the org during signup, then installs the GitHub App — not the other way around. Means the org ID exists before any integration, which is cleaner for billing and support. Downside: if user abandons mid-flow, we have empty orgs; mitigate by auto-deleting orgs that have no integrations + no users after 30 days.
- **Email verification with magic links**: users enter email, receive verification link, link completes signup. No password. (GitHub OAuth would also work but splits the "org name / billing email" identity from the "GitHub login for auth" identity. Magic link means one email = one org owner.)
- **GitHub App install flow**: standard OAuth-with-installation URL — GitHub redirects back with `installation_id`, our `/integrations/github/callback` route resolves the pending install and binds it to the current org. Phase 02 already set up the backend for this.
- **Repo picker**: after install, list all repos the install has access to, multi-select. Respect the tier's `max_repos` quota — show limit + counter inline.
- **Linear is optional**: skip button prominently displayed. Most orgs will be GitHub-only initially.
- **Invite flow**: admin enters emails, we send magic-link invites with embedded org reference. Accepting the invite creates a user account tied to that org (and only that org — a single human can be a member of multiple orgs, handled by a `user_orgs` pivot).
- **Domain matching guard**: warn (but don't block) when a user signs up with an email that matches an existing org's email domain. Prevents two people at the same company from accidentally creating parallel orgs. This is softening of the invite-only rule — shows "an org at @acme.com already exists — ask your admin for an invite, or continue to create a new one".

## Checklist

### Signup backend
- [ ] `POST /api/signup/start` — accepts `{email, org_name, org_slug}`, validates slug unique, sends magic link
- [ ] `POST /api/signup/verify` — accepts token from magic link, creates org row + first admin user row + returns JWT
- [ ] `POST /api/orgs/{org_id}/invite` — admin invites a user by email; sends magic link with `invite_token`
- [ ] `POST /api/signup/accept-invite` — accepts invite token, creates user record, issues JWT
- [ ] `GET /api/signup/domain-check?email=...` — returns existing orgs matching this email's domain (for the "already exists?" warning)

### Signup frontend
- [ ] `/signup` page — single-field email + org name + slug form, magic link explainer
- [ ] `/signup/verify?token=...` — completes signup, redirects to onboarding
- [ ] `/onboarding/github` — GitHub App install button, explainer text
- [ ] `/onboarding/repos` — multi-select repo picker with quota counter
- [ ] `/onboarding/linear` — optional API key entry with "skip for now"
- [ ] `/onboarding/invite` — optional teammate invite form
- [ ] `/onboarding/complete` — redirects to `/dashboard` with first-sync banner

### Onboarding checklist
- [ ] `onboarding_progress` table or embedded JSON column on `organizations`: `github_installed`, `repos_selected`, `first_sync_completed`, `team_invited`
- [ ] Dashboard card shows checklist items with links until all are true, then card hides

### Email delivery
- [ ] Add email service integration — pick Postmark or Resend (Postmark has better deliverability for transactional, Resend is cheaper). Config via env var, noop in dev/staging.
- [ ] Template for magic-link verify, invite, and "sync complete" notifications

### Security
- [ ] Magic link tokens: short-lived (15 min), single-use, stored hashed
- [ ] Rate limit signup attempts per IP (slowapi global key) — 5/hour — to prevent signup spam
- [ ] CAPTCHA on signup form — hCaptcha free tier — gated by env var so dev/staging skip it
- [ ] Slug uniqueness enforced at DB level (unique index on `organizations.slug`)
- [ ] Reserved slugs list (`admin`, `api`, `app`, `www`, `help`, `settings`, etc.) rejected at signup

### Testing
- [ ] E2E Playwright: new-user signup → email verify → GitHub install mock → repo pick → dashboard. All on staging.
- [ ] E2E: invite flow — admin invites test user, test user accepts, verifies membership in same org
- [ ] Abuse test: spam signup attempts rate-limited, CAPTCHA blocks automation in staging flag-on mode

## Risks

- **Mocking GitHub App install in E2E** is painful — the install happens on github.com and redirects back. Either (a) use a dedicated test GitHub App and a fixture test repo, (b) stub the install callback in test mode with a specific header that bypasses real GitHub. Decision pending — prefer (a) for realism.
- **Email deliverability** — magic links landing in spam break the signup UX. Use a warmed-up sender domain (possibly `noreply@devpulse.claros.no`) with SPF/DKIM/DMARC. Document in `docs/operations/email-setup.md`.
- **Abandoned orgs**: visitors who start signup, verify email, but never install the App leave empty orgs. Mitigate: scheduled cleanup job deletes orgs with 0 integrations + 1 user + age > 30 days. Worker tick handles it.
- **Invite-email-mismatch**: user invites `alice@acme.com` but Alice authenticates with `alice@gmail.com`. Mitigate: invite token is bound to the exact email; acceptance requires the same email in GitHub OAuth response OR explicit re-prompt.

## Out of scope (later phases)

- Stripe billing / upgrade UX — future epic
- SSO/SAML — future epic, needed for larger customers
- Password-based auth fallback — unlikely to ship, magic links are the standard
- Multi-org switcher for users who belong to multiple orgs — start with "one org per user" and expand if real customers ask for it
