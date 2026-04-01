# SA-11: Infrastructure Hardening (Backlog)

**Priority:** Backlog
**Severity:** LOW
**Effort:** Low
**Status:** Complete

## Findings

### Finding #23: Dockerfile Runs as Root
- **File:** `backend/Dockerfile`
- No `USER` directive — container processes run as root
- Container compromise = full filesystem access including the GitHub App PEM key

### Finding #24: Docker Socket Mounted in Promtail
- **File:** `docker-compose.yml:68-70`
- `/var/run/docker.sock` mounted in Promtail container
- Docker socket = root-equivalent access to host
- If Promtail is compromised, attacker gets host root access

## Required Changes

### 1. Add non-root user to backend Dockerfile — ALREADY DONE
- `backend/Dockerfile` already has `adduser appuser`, `COPY --chown=appuser:appuser`, and `USER appuser`
- PEM file readability depends on host permissions (must be world-readable or UID-matched)

### 2. Evaluate Docker socket necessity for Promtail
- Promtail uses the Docker socket to discover container labels for log routing
- Alternative: use file-based log collection (Promtail reads from `/var/log/`) without socket access
- If socket is required, document the risk and ensure Promtail image is pinned to a specific version

### 3. Remove `privileged: true` from cAdvisor — NOT APPLICABLE
- cAdvisor in `docker-compose.yml` does NOT have `privileged: true` (only read-only volume mounts)
- No action needed

### 4. Pin all infrastructure image versions — DONE
- Pinned `postgres:15` → `postgres:15.17` (all other images were already pinned)
- All observability images already versioned: loki:3.4.2, promtail:3.4.2, grafana:11.6.0, prometheus:v3.2.1, cadvisor:v0.51.0

## Impact Analysis

### Will this break anything?

**Non-root user — PEM file permission dependency.** The backend writes nothing to disk at runtime. The only concern is reading the PEM file mounted at `/app/github-app.pem:ro`. Whether the non-root `appuser` can read it depends on host file permissions — the file must be world-readable (`chmod 644`) or the container UID must match the host file owner. **This is an operational requirement that must be documented.**

**Promtail Docker socket — removal BREAKS log collection.** `infrastructure/promtail-config.yml` uses `docker_sd_configs` with `host: unix:///var/run/docker.sock` as its sole scrape mechanism. Removing the socket requires replacing with `static_configs` + file-based scrape jobs pointing at Docker's json-file log path (`/var/lib/docker/containers/*/*.log`). This loses dynamic container label discovery — service name labels would need regex relabeling from file paths. **Non-trivial migration.** Promtail image is already pinned (`grafana/promtail:3.4.2`), which partially mitigates the risk.

**cAdvisor privileged removal — should work.** cAdvisor needs `/sys`, `/var/lib/docker`, and Docker socket (all already volume-mounted read-only). Replacing `privileged: true` with `cap_add: [SYS_PTRACE]` + `security_opt: [apparmor:unconfined]` is the standard mitigation and works in most environments.

**Image pinning — only `postgres:15` needs it.** All observability images are already pinned:
- `grafana/loki:3.4.2`, `grafana/promtail:3.4.2`, `grafana/grafana:11.6.0`
- `prom/prometheus:v3.2.1`, `gcr.io/cadvisor/cadvisor:v0.51.0`
- `backend` and `frontend` are built locally (not a supply chain concern)
- Only `postgres:15` floats minor/patch versions — pin to e.g., `postgres:15.6`

**Missing `.dockerignore` — significant gap.** No `.dockerignore` exists. The `COPY . .` in `backend/Dockerfile` copies `.env`, `*.pem`, `__pycache__`, `tests/`, `.git` into the image. Must create with at minimum: `.env`, `*.pem`, `tests/`, `*.pyc`, `__pycache__`, `.git`, `.claude/`.

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/Dockerfile` | Already has `USER appuser` — no change needed | N/A |
| `backend/.dockerignore` (new) | Created — excludes `.env`, `*.pem`, `tests/`, `*.pyc`, `.git`, `.claude/` | None |
| `docker-compose.yml:~97` | cAdvisor has no `privileged: true` — no change needed | N/A |
| `docker-compose.yml:~2` | Pinned `postgres:15` → `postgres:15.17` | None |

### What to defer

- Promtail Docker socket removal — non-trivial migration, low severity, image already pinned. Document the risk instead.

## Testing

- Verify cAdvisor starts and collects metrics with reduced capabilities
- Verify backend container runs as non-root and can read PEM file
- Verify `.dockerignore` prevents sensitive files from entering the image (`docker build` then inspect)
- Verify Promtail still collects logs (socket remains for now)
