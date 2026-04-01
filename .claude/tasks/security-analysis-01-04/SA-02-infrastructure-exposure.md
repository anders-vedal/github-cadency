# SA-02: Fix Infrastructure Service Exposure

**Priority:** Immediate
**Severity:** CRITICAL (Grafana), HIGH (PostgreSQL, Loki, Prometheus)
**Effort:** Low
**Status:** Complete

## Findings

### Finding #3: Grafana Anonymous Admin Access
- **File:** `docker-compose.yml:80-82`
- `GF_AUTH_ANONYMOUS_ORG_ROLE: Admin` + `GF_AUTH_DISABLE_LOGIN_FORM: "true"`
- Port 3002 bound to `0.0.0.0` — anyone on the network gets full Grafana admin
- Can read all application logs, modify dashboards, add data sources

### Finding #7: PostgreSQL Exposed with Default Credentials
- **File:** `docker-compose.yml:8-9,25`
- Port `5432` mapped to `0.0.0.0` with `devpulse:devpulse` credentials
- No SSL configured on `create_async_engine` (`backend/app/models/database.py:6`)
- Database contains plaintext Slack bot token and all app data

### Finding #14: Loki and Prometheus Exposed Without Auth
- **File:** `docker-compose.yml:58-60,97-109`, `infrastructure/loki-config.yml:1`
- Loki: `auth_enabled: false`, port 3100 on `0.0.0.0` — 90 days of logs queryable
- Prometheus: port 9090 on `0.0.0.0` — container metrics exposed
- cAdvisor: `privileged: true` with Docker socket mount

## Required Changes

### 1. Grafana auth (`docker-compose.yml`)
- Change `GF_AUTH_ANONYMOUS_ORG_ROLE` to `Viewer` (or disable anonymous auth entirely)
- Set `GF_AUTH_DISABLE_LOGIN_FORM: "false"` and configure admin credentials via env vars
- Bind port to `127.0.0.1:3002:3000`

### 2. PostgreSQL network binding (`docker-compose.yml`)
- Change `"5432:5432"` to `"127.0.0.1:5432:5432"`
- Move credentials to `.env` (not hardcoded in docker-compose.yml)
- Add comment in `.env.example` that production deployments must change the default password

### 3. Loki auth (`infrastructure/loki-config.yml`, `docker-compose.yml`)
- Bind Loki port to `127.0.0.1:3100:3100`
- Consider enabling `auth_enabled: true` if multi-tenant

### 4. Prometheus and cAdvisor (`docker-compose.yml`)
- Bind Prometheus to `127.0.0.1:9090:9090`
- Bind cAdvisor to `127.0.0.1:8080:8080`
- Remove `privileged: true` from cAdvisor (use specific capabilities instead)
- Evaluate if Docker socket mount is necessary for Promtail; if so, document the risk

### 5. Database SSL (stretch goal)
- Add `connect_args={"ssl": "prefer"}` to `create_async_engine` in `backend/app/models/database.py`
- Add PostgreSQL SSL config to docker-compose

## Impact Analysis

### Will this break anything?

**Binding to 127.0.0.1 — safe.** Docker inter-container communication uses the container network bridge (Docker DNS: `loki`, `db`, `prometheus`), NOT host port mappings. Verified:
- `infrastructure/grafana/provisioning/datasources/datasources.yml` uses `http://loki:3100` and `http://prometheus:9090`
- `infrastructure/promtail-config.yml` pushes to `http://loki:3100/loki/api/v1/push`
- `docker-compose.yml:25` uses `DATABASE_URL=...@db:5432`

All internal communication is unaffected. Only external host access is restricted.

**Grafana auth change — safe.** Provisioned dashboards and data sources are applied server-side at startup, independent of auth config. Changing anonymous role to `Viewer` or enabling the login form does not affect provisioned resources.

**Database SSL — DO NOT implement.** `backend/app/models/database.py:6` creates the engine from `settings.database_url` with no `connect_args`. Adding `connect_args={"ssl": "prefer"}` breaks the test suite, which uses `aiosqlite` (SQLite doesn't support SSL). If implemented, must be conditional on `postgresql` in the URL. **Defer to a separate task.**

**Observability services are opt-in.** Loki/Promtail/Grafana/Prometheus/cAdvisor all have `profiles: ["logging"]` — they only start with `--profile logging`. The PostgreSQL fix applies to the always-on stack.

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `docker-compose.yml:8` | `"127.0.0.1:5432:5432"` | None — internal uses `db:5432` |
| `docker-compose.yml:~60` | `"127.0.0.1:3100:3100"` | None — internal uses `loki:3100` |
| `docker-compose.yml:~77` | `"127.0.0.1:3002:3000"` | None |
| `docker-compose.yml:~97` | `"127.0.0.1:9090:9090"` | None |
| `docker-compose.yml:~105` | `"127.0.0.1:8080:8080"` | None |
| `docker-compose.yml:80-82` | Grafana: `GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer`, enable login form | None |
| `CLAUDE.md` | Update port references in observability table (documentation only) | None |

### What to skip

- Database SSL (`connect_args`) — breaks aiosqlite tests. Separate task if needed.
- Loki `auth_enabled: true` — adds complexity with no benefit for single-tenant local deployment. Binding to 127.0.0.1 is sufficient.

## Testing

- Verify all services still communicate within the Docker network after bind address changes
- Confirm Grafana requires login (or is Viewer-only for anonymous)
- Confirm external connections to DB port are refused
- Confirm Loki/Prometheus are not reachable from host network (unless accessed via 127.0.0.1)
