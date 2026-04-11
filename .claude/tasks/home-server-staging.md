# GitHub Cadency (DevPulse) — home-server staging stack

**Status:** Not Started
**Priority:** Low
**Type:** infrastructure
**Apps:** cross-app
**Effort:** small

DevPulse tracks developer activity (PRs, reviews, cycle times) across GitHub repos via a read-only GitHub App. Self-contained — no direct integration with other Nordlabs apps. Probably the easiest of the 5 non-Claros rollouts.

## Current state on the home server (as of 2026-04-11)

- `/opt/pipeline/workspaces/github-cadency/` — cloned, on `main` at `89653fe`
- `/opt/github-cadency-staging/` — cloned, owned by `github-cadency:github-cadency` system user (in docker group)
- `/var/lib/github-cadency-staging/{postgres,redis,minio,caddy-data,caddy-config}/` — empty bind-mount dirs
- `/opt/github-cadency-staging/.env.staging` — placeholder (0600)
- Existing compose files in the repo: `docker-compose.yml`, `docker-compose.override.yml`
- Already has: `VERSION` = 0.1.0 ✅, `error-triage.yml` ✅, Loki/Promtail/Prometheus configs in repo ✅
- Missing: `/pipeline` command, staging stack
- **No** separate `docker-compose.prod.yml` yet — prod deploy story is still TBD

## Work needed in the github-cadency repo

- [ ] `infrastructure/docker-compose.staging.yml` — backend + frontend + Postgres + Caddy. DevPulse is read-only so no MinIO, no Redis (unless job queue added).
- [ ] `infrastructure/Caddyfile.staging` — HTTP-only, `devpulse-staging.claros.no` (or `github-cadency-staging.claros.no`) → frontend + `/api/*` → backend
- [ ] `infrastructure/.env.staging.example` — GitHub App **test installation** private key (not prod), `EMAIL_PROVIDER=noop`, `SENTINEL_URL=` empty
- [ ] `.github/workflows/deploy-staging.yml` — self-hosted runner
- [ ] `.github/workflows/deploy-prod.yml` — deferred until a prod target exists
- [ ] `infrastructure/scripts/build-images.sh` + `migrate.sh`
- [ ] `.claude/commands/pipeline.md` + `.claude/linear.json`
- [ ] Version build args following the standard pattern

## Work needed on the home server

- [ ] New cloudflared tunnel: `cloudflared tunnel create devpulse-staging` (or `github-cadency-staging`)
- [ ] DNS: `devpulse-staging.claros.no` CNAME → `<tunnel-uuid>.cfargotunnel.com`
- [ ] Sudoers allowlist: add `sudo -u github-cadency` commands
- [ ] First manual deploy + verify the GitHub App test installation can ingest one repo's PR history
- [ ] Register in Sentinel

## GitHub App gotcha

The DevPulse GitHub App has a private key at `github-app.pem` in the repo (flagged by earlier directory listing). That key must NOT be committed — verify `.gitignore` covers it and rotate the current one if it was ever pushed. Staging should use a **separate** GitHub App installation (e.g., a second "DevPulse (staging)" app) so prod-scoped data doesn't bleed into staging.

## Done when

- `https://devpulse-staging.claros.no/` serves the frontend, 200 OK via Cloudflare Tunnel
- A test repo's PR history is visible in staging DevPulse
- Deploy-staging auto-runs on push to main
- Pipeline runner can process `@implement` and `@brainstorm` with `github-cadency` label
