# Switch GitHub sync from org-scoped to installation-scoped endpoints

**Status:** Planned
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** medium

## Overview

DevPulse today assumes the tracked GitHub account is an **Organization** and hard-codes `/orgs/{GITHUB_ORG}/...` endpoints for repo discovery, contributor sync, and OAuth sign-in gating. This blocks using DevPulse against a **User account** (the installation on `anders-vedal` personal repos is a User-account install — GitHub's `/orgs/anders-vedal/...` endpoints return 404).

Switch the sync to the GitHub App's **installation-scoped** endpoints (`/installation/repositories`), which work uniformly for User and Org installations. Replace the org-membership OAuth check with an explicit `DEVPULSE_ALLOWED_USERS` allowlist env var. `GITHUB_ORG` becomes optional (repurposed as an optional display label).

## Why this matters

- Installation `125825336` is on `anders-vedal` (User), not an org. The current code cannot sync it.
- GitHub Apps are architected around installation tokens — using installation-scoped endpoints is the idiomatic path and also removes one layer of config (the org name) that has to stay in sync with reality.
- Prod has been silently syncing HELP-Forsikring repos because `GITHUB_ORG=HELP-Forsikring` was never updated after the App was swapped to `devpulse-cadency` on 2026-04-21. Fixing this closes that drift too.

## Scope

- `discover_org_repos` and `run_sync`: replace `/orgs/{org}/repos` → `/installation/repositories`
- `sync_org_contributors`: drop the `/orgs/{org}/members` fetch; contributors are already resolved from PR authors via `resolve_author`
- `oauth.py`: replace org-membership gating with `DEVPULSE_ALLOWED_USERS` allowlist (comma-separated GitHub usernames, required)
- `config.py`: `GITHUB_ORG` becomes optional; startup check removed or demoted to a warning. Add `devpulse_allowed_users` setting.
- `main.py`: Sentinel `source_id` falls back sensibly when `GITHUB_ORG` is unset
- Local + prod `.env` swap: new App credentials already present in prod; pull them from prod's container into local `.env`. Drop or blank out `GITHUB_ORG`. Add `DEVPULSE_ALLOWED_USERS=anders-vedal`.

## Out of scope

- Multi-tenant / multi-installation — one installation per DevPulse deployment remains the assumption. The multi-tenancy epic covers multi-installation.
- Per-repo collaborator enrichment — contributors continue to be derived from PR authors.
- Webhook handling for installation events (new repos added/removed) — future enhancement.

## Phases

- [ ] Phase 1: Installation-scoped repo + contributor discovery → `installation-scoped-sync/01-installation-scoped-discovery.md`
- [ ] Phase 2: OAuth allowlist gating → `installation-scoped-sync/02-oauth-allowlist-gating.md`
- [ ] Phase 3: Env swap + wipe + validate → `installation-scoped-sync/03-env-swap-and-validate.md`

## Acceptance criteria

- [ ] `GITHUB_ORG` unset → app starts cleanly, sync discovers repos via installation token
- [ ] Sync against personal `anders-vedal` installation populates `repositories`, `pull_requests`, `developers` correctly
- [ ] OAuth sign-in with a GitHub user not in `DEVPULSE_ALLOWED_USERS` → 403 with a clear message
- [ ] Both local and prod pointed at the `devpulse-cadency` App (ID 3453336) + installation 125825336 (anders-vedal personal)
- [ ] Pre-wipe data from HELP-Forsikring does not come back after re-sync
