# Phase 3: Env swap + wipe + validate

**Status:** 🔄 In Progress
**Priority:** High
**Type:** infrastructure
**Apps:** devpulse
**Effort:** small
**Parent:** installation-scoped-sync/00-overview.md
**Dependencies:** installation-scoped-sync/01-installation-scoped-discovery.md, installation-scoped-sync/02-oauth-allowlist-gating.md

## Scope

Swap local + prod `.env` to the `devpulse-cadency` App (ID 3453336) + installation `125825336` on `anders-vedal` personal account. Drop `GITHUB_ORG=HELP-Forsikring`. Add `DEVPULSE_ALLOWED_USERS=anders-vedal`. Wipe both DBs again and verify personal repos sync.

## Files touched

- `.env` (local)
- `/etc/devpulse/.env` (prod, via deploy user)

## Source values

All correct values already live in prod's running backend container — pull from there rather than re-generating secrets:

| Var | Value / source |
|---|---|
| `GITHUB_APP_ID` | `3453336` |
| `GITHUB_APP_INSTALLATION_ID` | `125825336` |
| `GITHUB_CLIENT_ID` | `Iv23liWJn3lW5xE9g3eq` |
| `GITHUB_CLIENT_SECRET` | prefix `04ffd2...` — pull from `docker exec devpulse-backend-1 env` on prod |
| `GITHUB_WEBHOOK_SECRET` | prefix `ba0dd0...` — pull from `docker exec devpulse-backend-1 env` on prod |
| `GITHUB_APP_PRIVATE_KEY_PATH` | `./github-app.pem` (local) or `/etc/devpulse/github-app.pem` (prod) — PEM already matches new App, no change |
| `GITHUB_ORG` | unset (or blank) |
| `DEVPULSE_ALLOWED_USERS` | `anders-vedal` |
| `DEVPULSE_INITIAL_ADMIN` | `anders-vedal` (keep) |

## Checklist

- [ ] Pull `GITHUB_CLIENT_SECRET` + `GITHUB_WEBHOOK_SECRET` from prod backend container into local `.env`
- [ ] Overwrite local `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_CLIENT_ID` with prod values
- [ ] Comment out or remove `GITHUB_ORG` in local `.env`
- [ ] Add `DEVPULSE_ALLOWED_USERS=anders-vedal` to local `.env`
- [ ] Recreate local backend container to pick up new env: `docker compose up -d --force-recreate backend`
- [ ] Wipe local DB: `docker exec github-cadency-db-1 psql -U devpulse -d devpulse -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO devpulse;'` then restart backend so Alembic re-runs
- [ ] OAuth sign-in locally → expect success as admin
- [ ] Trigger sync → expect anders-vedal personal repos populated
- [ ] Repeat for prod: edit `/etc/devpulse/.env` (requires deploy user access — may need user to run the edit), `docker compose up -d --force-recreate backend`, wipe schema, restart, verify sync

## Prod edit approach

Prod `/etc/devpulse/.env` is owned by `deploy` user with mode 0600 — not directly editable by `claros`. Options:

1. **User SSHes as deploy** and edits directly (if they have the key)
2. **User edits via console** on Hetzner and runs the docker commands themselves
3. **Sudoers one-liner** — user could add a narrow `claros ALL=(deploy) NOPASSWD: /usr/bin/sed -i ...` but that's overkill for a one-off

Recommend (1) or (2) — one-time manual edit.

## Testing

- [ ] Local: OAuth as `anders-vedal` → admin. OAuth as anyone else → 403.
- [ ] Local: `/api/integrations/linear` → sync populates `external_sprints`, `external_issues` from personal Linear workspace
- [ ] Local: GitHub sync populates `repositories` with personal repos only, no HELP-Forsikring repos
- [ ] Prod: same validations on `devpulse.claros.no`

## Cleanup

- [ ] Delete `backend/devpulse-cadency.2026-04-21.private-key.pem` (duplicate — `github-app.pem` already has the same content, verified via `diff`)
- [ ] If `GITHUB_ORG` is fully removed from config, remove from `.env.example` too

## Risks

- Running the wipe + sync against the wrong installation would pull unexpected repos. Double-check the installation ID before re-running sync.
- If `DEVPULSE_ALLOWED_USERS` is missing in prod at first sign-in, admin is locked out. Mitigate by deploying Phase 2 code + setting the env var in the same maintenance window.
