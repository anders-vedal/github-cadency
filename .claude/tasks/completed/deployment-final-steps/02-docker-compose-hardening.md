# Task 2: Harden docker-compose.yml for Production

**Status:** done
**Blocked by:** Task 1 (frontend Dockerfile)
**Blocks:** Task 3 (.env.example)

## Problem

`docker-compose.yml` has hardcoded DB passwords, no restart policies, and missing log rotation on some services.

## Changes Required

### 2a. Move hardcoded DB password to env var

**Current (`docker-compose.yml` lines 5-7):**
```yaml
db:
  image: postgres:15.17
  environment:
    POSTGRES_USER: devpulse
    POSTGRES_PASSWORD: devpulse
    POSTGRES_DB: devpulse
```

**Change to:**
```yaml
db:
  image: postgres:15.17
  environment:
    POSTGRES_USER: devpulse
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-devpulse}
    POSTGRES_DB: devpulse
```

**Also update backend `DATABASE_URL` (line 25):**

Current:
```yaml
DATABASE_URL: postgresql+asyncpg://devpulse:devpulse@db:5432/devpulse
```

Change to:
```yaml
DATABASE_URL: postgresql+asyncpg://devpulse:${POSTGRES_PASSWORD:-devpulse}@db:5432/devpulse
```

**Why `:-devpulse` default:** Local dev works without any `.env` changes. Production `.env` sets `POSTGRES_PASSWORD=<strong-random>` which overrides the default. This is the standard Docker Compose pattern for env var substitution with fallbacks.

### 2b. Add `restart: unless-stopped` to core services

Add to `db`, `backend`, and `frontend`:
```yaml
restart: unless-stopped
```

**Why `unless-stopped` (not `always`):**
- `always`: restarts even after manual `docker compose stop` — annoying during maintenance
- `unless-stopped`: restarts after crashes, Docker daemon restart, VM reboot — but respects manual stops
- The observability stack services (loki, grafana, etc.) don't need this since they're opt-in and don't hold critical state

### 2c. Add log rotation to `db` and `frontend`

Backend already has log rotation (lines 30-34). Add the same config to `db` and `frontend`:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

**Why this matters:** Without log rotation, Docker stores container stdout/stderr in JSON files that grow unbounded. A busy PostgreSQL container can generate gigabytes of logs over weeks. With this config, each service keeps at most 30MB of logs (3 files x 10MB).

### 2d. No changes needed (already correct)

- **DB port binding:** `127.0.0.1:5432:5432` — only accessible from localhost. If this were `5432:5432`, the DB would be exposed to the network.
- **Observability stack:** Behind `profiles: ["logging"]` — not started by default `docker compose up`.
- **Override file:** `docker-compose.override.yml` is only auto-loaded by bare `docker compose up`. Production uses `docker compose -f docker-compose.yml up -d` explicitly.

## Expected Result

Full `docker-compose.yml` after changes (core services only):

```yaml
services:
  db:
    image: postgres:15.17
    restart: unless-stopped
    environment:
      POSTGRES_USER: devpulse
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-devpulse}
      POSTGRES_DB: devpulse
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U devpulse"]
      interval: 5s
      timeout: 5s
      retries: 5
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  backend:
    build: ./backend
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://devpulse:${POSTGRES_PASSWORD:-devpulse}@db:5432/devpulse
      LOG_FORMAT: json
    depends_on:
      db:
        condition: service_healthy
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "3001:5173"
    environment:
      - CI=true
      - API_URL=http://backend:8000
    depends_on:
      - backend
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

## Verification

```bash
# Verify env var substitution works
POSTGRES_PASSWORD=testpass docker compose -f docker-compose.yml config | grep testpass
# Should appear in both db.environment and backend.environment

# Verify default still works (no .env needed for local dev)
docker compose config | grep "POSTGRES_PASSWORD: devpulse"

# Verify restart policy
docker compose -f docker-compose.yml config | grep restart
# Should show "unless-stopped" for db, backend, frontend
```
