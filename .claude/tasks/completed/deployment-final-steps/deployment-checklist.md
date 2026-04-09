# Deployment Checklist — Publishing DevPulse for Company Use

## Deployment Strategy

Deploy a **single shared instance** on a VM behind VPN + IP whitelist. Auto-deploy via GitHub Actions on push to main. Three-layer access control: VPN → IP whitelist (Caddy) → GitHub OAuth (org-scoped).

---

## Task 1: Make the frontend Dockerfile production-ready

**Problem:** The current `frontend/Dockerfile` runs `pnpm dev --host` (Vite dev server). In production we need a static build served by nginx or similar.

**Current state (`frontend/Dockerfile`):**
```dockerfile
FROM node:22-slim
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --no-frozen-lockfile
COPY . .
CMD ["sh", "-c", "pnpm install --no-frozen-lockfile && pnpm dev --host"]
```

**What to change:**
- Multi-stage build: Stage 1 (`node:22-slim`) runs `pnpm build` (which does `tsc -b && vite build`). Stage 2 (`nginx:alpine`) serves the static `dist/` folder.
- The nginx stage needs a config that:
  - Serves `index.html` for all routes (SPA fallback)
  - Proxies `/api/*` to the backend container at `http://backend:8000`
  - This replaces the Vite dev proxy (`vite.config.ts` proxy is dev-only)
- The dev override (`docker-compose.override.yml`) continues to use the old CMD for hot-reload.

**New `frontend/Dockerfile`:**
```dockerfile
# Stage 1: Build
FROM node:22-slim AS build
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 5173
```

**New `frontend/nginx.conf`:**
```nginx
server {
    listen 5173;

    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback — all non-file routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy to backend container
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Cache static assets
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

**Update `docker-compose.override.yml`** to override the CMD back to dev mode:
```yaml
frontend:
  build:
    context: ./frontend
    target: build          # use only stage 1
  command: ["sh", "-c", "pnpm install --no-frozen-lockfile && pnpm dev --host"]
  volumes:
    - ./frontend:/app
    - /app/node_modules
```

**Why port 5173:** Keep the same port so `docker-compose.yml` port mapping (`3001:5173`) doesn't change.

---

## Task 2: Harden docker-compose.yml for production

**File:** `docker-compose.yml`

### 2a. Move hardcoded DB password to env var

**Current (line 5-7):**
```yaml
environment:
  POSTGRES_USER: devpulse
  POSTGRES_PASSWORD: devpulse
  POSTGRES_DB: devpulse
```

**Change to:**
```yaml
environment:
  POSTGRES_USER: devpulse
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-devpulse}
  POSTGRES_DB: devpulse
```

Also update the backend `DATABASE_URL` (line 25) to use the same variable:
```yaml
DATABASE_URL: postgresql+asyncpg://devpulse:${POSTGRES_PASSWORD:-devpulse}@db:5432/devpulse
```

The `:-devpulse` default keeps local dev working without config changes. Production `.env` sets `POSTGRES_PASSWORD` to something strong.

### 2b. Add `restart: unless-stopped` to core services

Add to `db`, `backend`, and `frontend` services:
```yaml
restart: unless-stopped
```

This ensures containers auto-start after VM reboot or Docker daemon restart. `unless-stopped` (not `always`) respects manual `docker compose stop`.

### 2c. Add log rotation to frontend and db

Backend already has log rotation (lines 30-34). Add the same to `db` and `frontend`:
```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

Without this, container logs grow unbounded and can fill the disk.

### 2d. What's already correct (no changes needed)

- DB port bound to `127.0.0.1:5432:5432` — not externally accessible. Good.
- Observability stack behind `profiles: ["logging"]` — not started by default. Good.
- `docker-compose.override.yml` is only loaded by bare `docker compose up`. Production deploys use `docker compose -f docker-compose.yml up -d` explicitly, skipping the override. Good.

---

## Task 3: Update .env.example with production guidance

**File:** `.env.example`

### 3a. Add `POSTGRES_PASSWORD` variable

Add near the top, next to `DATABASE_URL`:
```bash
# PostgreSQL password — used by both the db container and backend DATABASE_URL.
# CHANGE THIS for any non-local deployment. Generate with: openssl rand -hex 16
POSTGRES_PASSWORD=devpulse
```

### 3b. Mark critical production variables

The file already has some guidance but needs clearer "MUST CHANGE" markers. Add a header section:
```bash
# ============================================================
# PRODUCTION CHECKLIST — change these before deploying:
#   1. POSTGRES_PASSWORD  (default: devpulse)
#   2. JWT_SECRET         (generate: openssl rand -hex 32)
#   3. ENCRYPTION_KEY     (generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
#   4. GITHUB_WEBHOOK_SECRET (generate: openssl rand -hex 32)
#   5. GITHUB_APP_ID / INSTALLATION_ID / PRIVATE_KEY_PATH
#   6. GITHUB_CLIENT_ID / CLIENT_SECRET
#   7. GITHUB_ORG
#   8. DEVPULSE_INITIAL_ADMIN
#   9. FRONTEND_URL       (set to https://your-domain)
#  10. ENVIRONMENT=production
#  11. LOG_FORMAT=json
#  12. GF_ADMIN_PASSWORD  (if using observability stack)
# ============================================================
```

### 3c. What's already correct

- Secret generation commands are already documented inline. Good.
- `ENVIRONMENT` already distinguishes dev/prod. Good.
- Rate limiting docs are clear. Good.

---

## Task 4: Add Caddy reverse proxy config with IP whitelist

**New file:** `infrastructure/Caddyfile`

```
# DevPulse reverse proxy — deployed on the host, outside Docker.
# Handles HTTPS termination + IP whitelist.
#
# Install: https://caddyserver.com/docs/install
# Start:  sudo caddy start --config /etc/caddy/Caddyfile
#
# Replace the domain and IP ranges below with your values.

devpulse.internal.company.com {
    # --- IP Whitelist ---
    # Only allow requests from VPN / office network ranges.
    # Deny everything else with 403.
    # Add your CIDR ranges below (comma-separated or multiple lines).
    @blocked not remote_ip 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16
    respond @blocked "Access denied" 403

    # --- Reverse proxy ---
    # API requests → backend container
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # Everything else → frontend container
    handle {
        reverse_proxy localhost:3001
    }
}
```

**Why Caddy outside Docker (not as a Docker service):**
- Caddy manages TLS certificates and needs persistent state across deploys
- Running it as a system service means `docker compose down` doesn't kill your TLS termination
- Simpler to manage separately — install once, config rarely changes
- If the team already uses nginx/Traefik, swap this for their standard

**Why not add IP whitelist in FastAPI middleware:**
- Network-level blocking is more secure — rejected requests never reach the app
- Caddy handles it before TLS termination overhead for blocked IPs
- Keeps security policy separate from application code

**TLS options:**
- If the domain is **publicly resolvable** (even if access is restricted): Caddy auto-provisions Let's Encrypt certs. Zero config needed.
- If **internal-only DNS**: use your company's internal CA. Add to Caddyfile:
  ```
  tls /path/to/cert.pem /path/to/key.pem
  ```

---

## Task 5: Add deploy helper scripts

**New directory:** `scripts/`

### 5a. `scripts/backup-db.sh`

```bash
#!/usr/bin/env bash
# Backs up the DevPulse PostgreSQL database.
# Usage: ./scripts/backup-db.sh [backup_dir]
#   backup_dir defaults to /backups

set -euo pipefail

BACKUP_DIR="${1:-/backups}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/devpulse-${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up database to ${BACKUP_FILE}..."
docker exec devpulse-db-1 pg_dump -U devpulse devpulse | gzip > "$BACKUP_FILE"
echo "Backup complete: ${BACKUP_FILE} ($(du -h "$BACKUP_FILE" | cut -f1))"

# Retention: delete backups older than 30 days
find "$BACKUP_DIR" -name "devpulse-*.sql.gz" -mtime +30 -delete
echo "Cleaned up backups older than 30 days."
```

### 5b. `scripts/deploy.sh`

```bash
#!/usr/bin/env bash
# Deploy DevPulse. Called by GitHub Actions CI/CD or manually.
# Usage: ./scripts/deploy.sh
#
# Expects:
#   - Working directory is the repo root (/opt/devpulse)
#   - .env file exists (or is symlinked from /etc/devpulse/.env)
#   - Docker Compose v2 is installed

set -euo pipefail

COMPOSE="docker compose -f docker-compose.yml"
BACKUP_DIR="/backups"

echo "=== DevPulse Deploy ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 1. Pull latest code (already done by CI, but idempotent)
echo "--- Pulling latest code ---"
git pull origin main

# 2. Pre-deploy backup
echo "--- Backing up database ---"
if docker ps --format '{{.Names}}' | grep -q devpulse-db-1; then
    ./scripts/backup-db.sh "$BACKUP_DIR"
else
    echo "Database container not running, skipping backup (first deploy?)"
fi

# 3. Build new images
echo "--- Building images ---"
$COMPOSE build

# 4. Restart services
echo "--- Starting services ---"
$COMPOSE up -d

# 5. Wait for health check
echo "--- Waiting for backend health check ---"
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "Backend is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Backend health check failed after 30 attempts"
        $COMPOSE logs backend --tail 20
        exit 1
    fi
    sleep 2
done

echo "=== Deploy complete ==="
```

### 5c. `scripts/rollback.sh`

```bash
#!/usr/bin/env bash
# Rollback to the previous git commit and redeploy.
# Optionally restore a database backup.
#
# Usage:
#   ./scripts/rollback.sh                    # rollback code only
#   ./scripts/rollback.sh --restore-db FILE  # also restore a DB backup

set -euo pipefail

COMPOSE="docker compose -f docker-compose.yml"
RESTORE_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --restore-db)
            RESTORE_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== DevPulse Rollback ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 1. Revert to previous commit
CURRENT=$(git rev-parse --short HEAD)
echo "Current commit: $CURRENT"
git checkout HEAD~1
echo "Rolled back to: $(git rev-parse --short HEAD)"

# 2. Restore DB backup if requested
if [ -n "$RESTORE_FILE" ]; then
    echo "--- Restoring database from $RESTORE_FILE ---"
    if [ ! -f "$RESTORE_FILE" ]; then
        echo "ERROR: Backup file not found: $RESTORE_FILE"
        exit 1
    fi
    gunzip < "$RESTORE_FILE" | docker exec -i devpulse-db-1 psql -U devpulse devpulse
    echo "Database restored."
fi

# 3. Rebuild and restart
echo "--- Rebuilding and restarting ---"
$COMPOSE build
$COMPOSE up -d

echo "=== Rollback complete ==="
echo "If this is stable, consider: git revert $CURRENT && git push"
```

### 5d. File permissions

All scripts need `chmod +x`. The CI workflow should handle this, or commit with executable bit set:
```bash
git update-index --chmod=+x scripts/backup-db.sh scripts/deploy.sh scripts/rollback.sh
```

---

## Task 6: Create GitHub Actions CI/CD deploy workflow

**New file:** `.github/workflows/deploy.yml`

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install backend dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Run backend tests
        run: |
          cd backend
          python -m pytest tests/ -x -q
        env:
          JWT_SECRET: test-secret-that-is-at-least-32-characters-long
          RATE_LIMIT_ENABLED: "false"

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Install pnpm
        run: corepack enable && corepack prepare pnpm@latest --activate

      - name: Build frontend
        run: |
          cd frontend
          pnpm install --frozen-lockfile
          pnpm build

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          key: ${{ secrets.DEPLOY_KEY }}
          script: |
            cd /opt/devpulse
            git pull origin main
            ./scripts/deploy.sh
```

**Required GitHub Actions secrets** (set in repo Settings → Secrets):

| Secret | Value | Example |
|--------|-------|---------|
| `DEPLOY_HOST` | Server IP or hostname | `10.0.1.50` or `devpulse.internal.company.com` |
| `DEPLOY_USER` | SSH username on server | `deploy` |
| `DEPLOY_KEY` | SSH private key (ed25519 recommended) | Contents of `~/.ssh/id_ed25519` |

**Server-side SSH setup:**
```bash
# On the deploy server:
# 1. Create a deploy user with Docker access
sudo adduser --disabled-password deploy
sudo usermod -aG docker deploy

# 2. Add the deploy public key
sudo mkdir -p /home/deploy/.ssh
echo "ssh-ed25519 AAAA... deploy-ci" | sudo tee /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys

# 3. Ensure deploy user owns the app directory
sudo chown -R deploy:deploy /opt/devpulse
```

**Flow:**
1. Push to `main` → triggers workflow
2. `test` job: runs pytest + frontend build (catches errors before deploy)
3. `deploy` job: SSHs into server, runs `scripts/deploy.sh`
4. `deploy.sh`: pulls code → backs up DB → builds images → restarts → health check

**If deploy fails:** The old containers keep running until `docker compose up -d` succeeds. If the new containers fail health checks, `deploy.sh` exits non-zero and GitHub Actions shows the failure. Manual rollback: SSH in and run `./scripts/rollback.sh`.

---

## Task 7: Write production deployment guide

**New file:** `docs/DEPLOYMENT.md`

This is the human-readable guide that ties everything together. It should cover:

### 7a. Prerequisites
- VM with Docker Engine + Docker Compose v2 (minimum 2 CPU, 4 GB RAM)
- Server on company VPN or internal network
- GitHub App created in your org (read-only permissions)
- SSH key pair for CI/CD deploy

### 7b. Server Setup (one-time)
1. Install Docker: `curl -fsSL https://get.docker.com | sh`
2. Install Caddy: link to official install docs
3. Create deploy user (see Task 6 SSH setup)
4. Clone repo to `/opt/devpulse`
5. Create `/etc/devpulse/.env` with production values (copied from `.env.example`)
6. Symlink: `ln -s /etc/devpulse/.env /opt/devpulse/.env`
7. Copy `github-app.pem` to `/opt/devpulse/github-app.pem` with `chmod 600`
8. Create backup directory: `mkdir -p /backups`
9. Configure Caddy: copy `infrastructure/Caddyfile` to `/etc/caddy/Caddyfile`, edit domain + IP ranges
10. Start Caddy: `sudo systemctl enable --now caddy`

### 7c. GitHub App Creation
Step-by-step with exact permission checkboxes:
- Repository: Contents (read), Pull requests (read), Issues (read), Checks (read), Metadata (read)
- Organization: Members (read)
- **No write permissions** — DevPulse is strictly read-only
- OAuth callback URL: `https://devpulse.internal.company.com/api/auth/callback`
- Webhook URL: `https://devpulse.internal.company.com/api/webhooks/github`
- Generate and download private key → save as `github-app.pem`

### 7d. Secret Generation
Exact commands (already in `.env.example`, repeated here for clarity):
```bash
# JWT_SECRET (min 32 chars)
openssl rand -hex 32

# ENCRYPTION_KEY (Fernet, for Slack bot token encryption)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# GITHUB_WEBHOOK_SECRET
openssl rand -hex 32

# POSTGRES_PASSWORD
openssl rand -hex 16
```

### 7e. CI/CD Setup
1. Generate SSH key pair: `ssh-keygen -t ed25519 -f deploy-key -N ""`
2. Add public key to server (see Task 6)
3. Add secrets to GitHub repo Settings → Secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY`
4. Push to `main` → watch GitHub Actions for first deploy

### 7f. First-Time Setup
1. Navigate to `https://devpulse.internal.company.com`
2. Log in with the GitHub account set as `DEVPULSE_INITIAL_ADMIN`
3. Go to Admin → Sync → Run first sync
4. Configure sync schedule (Admin → Sync → Schedule card)
5. Assign roles to developers (Admin → Team)

### 7g. Backup & Restore
- Automatic: `deploy.sh` backs up before every deploy
- Manual: `./scripts/backup-db.sh`
- Cron for daily backups: `0 3 * * * /opt/devpulse/scripts/backup-db.sh /backups`
- Restore: `gunzip < /backups/devpulse-YYYYMMDD-HHMMSS.sql.gz | docker exec -i devpulse-db-1 psql -U devpulse devpulse`

### 7h. Rollback
- Code only: `./scripts/rollback.sh`
- Code + DB: `./scripts/rollback.sh --restore-db /backups/devpulse-YYYYMMDD-HHMMSS.sql.gz`
- Permanent fix: `git revert <bad-commit> && git push` (triggers clean deploy)

### 7i. What NOT To Do
- Don't expose DevPulse to the public internet — it shows internal engineering metrics
- Don't give the GitHub App write permissions — DevPulse is strictly read-only
- Don't skip HTTPS — JWTs and API tokens flow over the wire
- Don't leave default passwords — especially `devpulse:devpulse` for PostgreSQL
- Don't run `docker compose up` without `-f docker-compose.yml` in production — the override file enables hot-reload and runs as root

---

## Architecture Decision Record

**Decision:** Single shared hosted instance behind VPN, auto-deployed via GitHub Actions SSH.

**Why not other approaches:**
- **Watchtower + GHCR:** Adds a container registry dependency for no real benefit. SSH deploy is simpler and the deploy workflow is more visible in GitHub Actions.
- **Kubernetes:** Massive overhead for a single-instance team tool. Docker Compose is sufficient.
- **Local instances per developer:** Multiplies GitHub API rate limit consumption, databases diverge, admin config not shared.
- **Shared DB + local frontends:** Frontend is a static SPA proxying to API — no benefit over hosted, adds version skew.

**Security layers (defense in depth):**
1. **VPN/network** — server only reachable from company network
2. **IP whitelist (Caddy)** — even within VPN, restrict to known CIDR ranges
3. **HTTPS (Caddy)** — all traffic encrypted, prevents credential sniffing
4. **GitHub OAuth** — only org members can authenticate
5. **JWT + role-based access** — admin vs developer permissions within the app
6. **Rate limiting** — prevents abuse even from authenticated users
