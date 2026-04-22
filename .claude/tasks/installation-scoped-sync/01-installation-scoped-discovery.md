# Phase 1: Installation-scoped repo + contributor discovery

**Status:** ✅ Completed
**Completed:** 2026-04-22
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** installation-scoped-sync/00-overview.md

## Scope

Replace the org-scoped GitHub endpoints with installation-scoped endpoints so the sync works uniformly for User and Org installations.

## Files touched

- `backend/app/services/github_sync.py` — 3 call sites: `discover_org_repos` (line ~2074), `run_sync` (line ~2184), `sync_org_contributors` (line ~586)
- `backend/app/config.py` — `github_org` becomes optional; startup check demoted to warning
- `backend/app/main.py` — Sentinel `source_id` fallback when `GITHUB_ORG` unset (line ~40)

## Checklist

- [ ] Swap `/orgs/{settings.github_org}/repos` → `/installation/repositories` in `discover_org_repos`. Response shape is `{"total_count": N, "repositories": [...]}` — unwrap `.repositories` before upserting. Pagination still works (`per_page`, cursor via `page`).
- [ ] Same swap in `run_sync` main loop — share a helper (`_fetch_installation_repos(ctx)`) to avoid duplication
- [ ] Drop `/orgs/{org}/members` call in `sync_org_contributors`. Developers are already auto-created via `resolve_author` on each PR/review/comment — the org members prefetch only seeded the `developers` table with people who might not have authored anything yet, which we don't strictly need. Either delete `sync_org_contributors` entirely or neuter it to a no-op with a warning log if `GITHUB_ORG` is set.
- [ ] `config.py`: change `github_org: str = ""` default semantics — no startup error if blank, just log an info line. Remove the `not settings.github_org` error branch.
- [ ] `main.py`: Sentinel `source_id=settings.github_org` → `source_id=settings.github_org or "devpulse"` (or similar fallback)
- [ ] Verify install token flow: `github_get_paginated` already mints installation tokens from the App's JWT + `GITHUB_APP_INSTALLATION_ID`, so no auth changes needed — just the URL path

## Testing

- [ ] Start local with `GITHUB_ORG` unset → `/api/sync/start` hits `/installation/repositories` and returns repos the App installation can see
- [ ] Sync completes without 404s
- [ ] `select count(*) from repositories;` matches the repos visible in https://github.com/settings/installations/125825336 after installation is scoped to the intended repos

## Risks

- `/installation/repositories` returns only what the installation has access to — if the user installed the App on "All repositories" for anders-vedal, that includes every public + private repo under their account. Recommend narrowing the install to a specific selection before running a sync, to avoid pulling in experiments / forks / archive repos.
- `sync_org_contributors` removal may leave the `developers` table sparser than before. Acceptable: DevPulse's metrics are computed from PR/review activity; non-contributing org members add noise.
