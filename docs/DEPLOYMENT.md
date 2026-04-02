# DevPulse Production Deployment Guide

This guide walks you through deploying DevPulse on a server. Follow the sections in order for a fresh deployment.

> **Multi-app server setup:** If you're hosting multiple apps on the same server (recommended), complete [HETZNER-SETUP.md](HETZNER-SETUP.md) first. It covers server provisioning, Caddy multi-site config, directory layout, port allocation, and shared CI/CD. Then return here for DevPulse-specific steps (sections 3-11).

---

## 1. Prerequisites

| Requirement | Details |
|-------------|---------|
| **Server** | 2 CPU, 4 GB RAM minimum for DevPulse alone. See [HETZNER-SETUP.md](HETZNER-SETUP.md) for multi-app sizing |
| **OS** | Ubuntu 22.04+ or Debian 12+ (any Linux with Docker support) |
| **Docker** | Docker Engine + Docker Compose v2 |
| **Reverse proxy** | Caddy (recommended), nginx, or Traefik for HTTPS termination. Multi-app Caddy setup in [HETZNER-SETUP.md](HETZNER-SETUP.md) |
| **Network** | Server on company VPN or internal network — DevPulse should **not** be exposed to the public internet |
| **GitHub** | A GitHub App installed on your organization (instructions in Section 3) |
| **CI/CD** | SSH key pair for automated deploys from GitHub Actions |

---

## 2. Server Setup (One-Time)

> **Using [HETZNER-SETUP.md](HETZNER-SETUP.md)?** If you already ran `server-bootstrap.sh` from that guide, skip to Section 2b — Docker, Caddy, deploy user, and directories are already set up.

### 2a. Automated setup (recommended)

The bootstrap script handles Docker, Caddy, deploy user, and directories in one command:

```bash
# On the server as root:
sudo ./scripts/server-bootstrap.sh "ssh-ed25519 AAAA... deploy-ci"
```

See [HETZNER-SETUP.md Section 6](HETZNER-SETUP.md#6-server-setup-one-time) for full instructions, or run each step manually by following the comments in `scripts/server-bootstrap.sh`.

### 2b. DevPulse-specific setup

After the server is bootstrapped and the repo is cloned to `/opt/devpulse`:

**Generate the .env file:**

```bash
su - deploy
cd /opt/devpulse
./scripts/generate-env.sh
```

This auto-generates all secrets (PostgreSQL password, JWT secret, encryption key, webhook secret) and prompts you for GitHub App values. It writes to `/etc/devpulse/.env` and creates the symlink to `/opt/devpulse/.env`.

Alternatively, manually copy and edit `.env.example` — see Section 4 for all variables.

**Upload the GitHub App private key** (from your local machine):

```bash
scp -i ~/.ssh/hetzner ~/Downloads/your-app.private-key.pem root@<server>:/etc/devpulse/github-app.pem
```

The bootstrap script pre-creates this file with `chmod 600`, so `scp` overwrites it with the correct permissions.

**Configure Caddy:**

For single-app deployments:

```bash
sudo cp /opt/devpulse/infrastructure/Caddyfile /etc/caddy/Caddyfile
```

Edit `/etc/caddy/Caddyfile`:
1. Replace `devpulse.internal.company.com` with your domain
2. Replace the IP ranges in the `@blocked` matcher with your VPN/office CIDR ranges
3. Configure TLS (see comments in the Caddyfile for options)

For multi-app deployments, see [HETZNER-SETUP.md Section 7](HETZNER-SETUP.md#7-caddy-configuration-multi-app).

```bash
sudo systemctl enable --now caddy
```

**Configure firewall** (if not using Hetzner Cloud Firewall):

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

> If using Hetzner Cloud Firewall (see [HETZNER-SETUP.md Section 3](HETZNER-SETUP.md#3-create-a-firewall)), `ufw` is optional — the cloud firewall blocks ports before they reach the server.

**Make deploy scripts executable:**

```bash
chmod +x /opt/devpulse/scripts/*.sh
```

---

## 3. GitHub App Creation

Create a GitHub App at `https://github.com/organizations/<your-org>/settings/apps/new`.

### App settings

| Field | Value |
|-------|-------|
| **App name** | DevPulse (or any name) |
| **Homepage URL** | `https://<your-domain>` |
| **Callback URL** | `https://<your-domain>/api/auth/callback` |
| **Webhook URL** | `https://<your-domain>/api/webhooks/github` |
| **Webhook secret** | Generate with `openssl rand -hex 32` (save this for `.env`) |

### Repository permissions (read-only)

- **Contents**: Read
- **Pull requests**: Read
- **Issues**: Read
- **Checks**: Read
- **Metadata**: Read

### Organization permissions

- **Members**: Read

> **No write permissions.** DevPulse is strictly read-only — it never writes back to GitHub.

### After creation

1. Note the **App ID** from the app settings page
2. Generate a **private key** (.pem) — download and save to the server (Section 2)
3. Under **OAuth**, note the **Client ID** and generate a **Client Secret**
4. **Install** the app on your organization → select which repositories to track
5. Note the **Installation ID** from the URL after installing (`.../installations/<id>`)

---

## 4. Production `.env` Configuration

**Recommended:** Use `./scripts/generate-env.sh` (see Section 2b) — it auto-generates all secrets and prompts for GitHub App values interactively.

**Manual alternative:** Copy `.env.example` and edit every value. Generate secrets with these commands:

```bash
# JWT secret (32+ hex chars)
openssl rand -hex 32

# PostgreSQL password
openssl rand -hex 16

# GitHub webhook secret
openssl rand -hex 32

# Encryption key (required for Slack token storage)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Variable reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password (change from default!) | `a3f8...` (output of `openssl rand -hex 16`) |
| `DATABASE_URL` | Yes | Must match `POSTGRES_PASSWORD`. In Docker, host is `db` | `postgresql+asyncpg://devpulse:<password>@db:5432/devpulse` |
| `JWT_SECRET` | Yes | Signs auth tokens. Min 32 chars | `e7b2...` (output of `openssl rand -hex 32`) |
| `GITHUB_APP_ID` | Yes | From GitHub App settings | `123456` |
| `GITHUB_APP_PEM_HOST_PATH` | Yes | Host path to `.pem` file (mounted into container by docker-compose) | `/etc/devpulse/github-app.pem` |
| `GITHUB_APP_INSTALLATION_ID` | Yes | From app installation URL | `78901234` |
| `GITHUB_WEBHOOK_SECRET` | Yes | Must match the webhook secret set in GitHub App | `d4a1...` (output of `openssl rand -hex 32`) |
| `GITHUB_ORG` | Yes | Your GitHub organization name | `my-company` |
| `GITHUB_CLIENT_ID` | Yes | OAuth Client ID from GitHub App | `Iv1.xxxxxxxxxxxx` |
| `GITHUB_CLIENT_SECRET` | Yes | OAuth Client Secret from GitHub App | `xxxxxxxxxxxxxxxxxxxx` |
| `DEVPULSE_INITIAL_ADMIN` | Yes | GitHub username of the first admin user | `your-username` |
| `FRONTEND_URL` | Yes | Your production URL (used for CORS) | `https://devpulse.internal.company.com` |
| `ENCRYPTION_KEY` | Yes | Fernet key for encrypting Slack tokens | `abc...=` (output of Fernet command) |
| `ENVIRONMENT` | Yes | Set to `production` (disables /docs, /redoc, enables HSTS) | `production` |
| `LOG_FORMAT` | Yes | Set to `json` for structured Docker logging | `json` |
| `LOG_LEVEL` | No | Log verbosity | `INFO` (default) |
| `RATE_LIMIT_ENABLED` | No | IP-based rate limiting | `true` (default) |
| `ANTHROPIC_API_KEY` | No | Only if using AI analysis features | `sk-ant-...` |
| `SYNC_INTERVAL_MINUTES` | No | Auto-sync interval | `15` (default) |
| `FULL_SYNC_CRON_HOUR` | No | Hour (UTC) for daily full sync | `2` (default) |
| `DEPLOY_WORKFLOW_NAME` | No | GitHub Actions workflow name for DORA metrics | _(empty = disabled)_ |
| `DEPLOY_ENVIRONMENT` | No | GitHub Actions environment name for DORA deploy tracking | `production` |
| `HOTFIX_LABELS` | No | Comma-separated PR labels that indicate hotfixes (DORA CFR detection) | `hotfix,urgent,incident` |
| `HOTFIX_BRANCH_PREFIXES` | No | Comma-separated branch prefixes that indicate hotfixes (DORA CFR detection) | `hotfix/` |
| `RATELIMIT_STORAGE_URI` | No | Redis URI for rate limit state in multi-instance deployments | `redis://localhost:6379` |
| `GF_ADMIN_USER` | No | Grafana admin username (if using observability) | `admin` |
| `GF_ADMIN_PASSWORD` | No | Grafana admin password (change from default!) | `<strong password>` |

> **Important — `DATABASE_URL` in Docker:** `docker-compose.yml` overrides `DATABASE_URL` to `postgresql+asyncpg://devpulse:<POSTGRES_PASSWORD>@db:5432/devpulse`. **Do not set `DATABASE_URL` in `.env` for Docker deployments** — it will be ignored. Only `POSTGRES_PASSWORD` matters. The `DATABASE_URL` in `.env.example` is for local (non-Docker) development only.

> **Important — GitHub App PEM paths:** There are two path variables because of Docker volume mounting:
> - `GITHUB_APP_PEM_HOST_PATH` — the path on the **host machine** (e.g., `/etc/devpulse/github-app.pem`). This is what `docker-compose.yml` uses to mount the file into the container.
> - `GITHUB_APP_PRIVATE_KEY_PATH` — the path **inside the container**. This is overridden by `docker-compose.yml` to `/etc/devpulse/github-app.pem`. You don't need to change it.
>
> In `.env`, only set `GITHUB_APP_PEM_HOST_PATH` to the host path where you placed the `.pem` file.

---

## 5. CI/CD Setup

### Generate an SSH deploy key

```bash
ssh-keygen -t ed25519 -f deploy-key -N ""
```

### Configure the server

> If you ran `server-bootstrap.sh` and provided the deploy key, this is already done — skip to "Add GitHub repository secrets" below.

```bash
# On the server, as the deploy user:
sudo -u deploy mkdir -p /home/deploy/.ssh
sudo -u deploy chmod 700 /home/deploy/.ssh

# Append the public key
cat deploy-key.pub | sudo -u deploy tee -a /home/deploy/.ssh/authorized_keys
sudo -u deploy chmod 600 /home/deploy/.ssh/authorized_keys
```

### Add GitHub repository secrets

In your repo → Settings → Secrets and variables → Actions, add:

| Secret | Value |
|--------|-------|
| `DEPLOY_HOST` | Server IP or hostname |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_KEY` | Contents of `deploy-key` (private key) |

### How it works

The `.github/workflows/deploy.yml` workflow:
1. **On every push to `main`**: runs backend tests (pytest) and frontend build check
2. **After tests pass**: SSHs to the server, pulls latest code, runs `./scripts/deploy.sh`
3. **Concurrency lock**: only one deploy runs at a time — a second push queues behind the active deploy, but a third push while one is queued replaces the queued run

### Network requirements

GitHub Actions runners need SSH access to your server. If the server has no public IP:
- Use a bastion/jump host and configure `ProxyJump` in the SSH config
- Use a self-hosted GitHub Actions runner on your internal network
- Set up a VPN tunnel from the runner

---

## 6. First Deploy

On the server, run the first deploy manually:

```bash
cd /opt/devpulse

# Start the database first
docker compose -f docker-compose.yml up -d db

# Wait for it to be healthy, then run migrations
docker compose -f docker-compose.yml run --rm backend alembic upgrade head

# Start all services
docker compose -f docker-compose.yml up -d
```

Wait for services to start, then verify:

```bash
# Check all containers are running
docker compose -f docker-compose.yml ps

# Check backend health
curl -sf http://localhost:8000/api/health
# Expected: {"status":"ok"}
```

After this, all subsequent deploys happen automatically via CI/CD on push to `main`.

---

## 7. First-Time App Setup

1. Open `https://<your-domain>` in your browser
2. Log in with the GitHub account set as `DEVPULSE_INITIAL_ADMIN`
3. Go to **Admin → Sync** → run your first sync
4. Go to **Admin → Sync** → configure the sync schedule (auto-sync interval, full sync hour)
5. Go to **Admin → Team** → assign roles to developers (used for benchmarks and metrics grouping)

---

## 8. Operations

### Backups

**Automatic pre-deploy backup:** `deploy.sh` backs up the database before every deploy.

**Manual backup:**

```bash
./scripts/backup-db.sh
# Output: /backups/devpulse-20260401-120000.sql.gz
```

**Scheduled backup via cron:**

```bash
# As the deploy user:
crontab -e
# Add: daily backup at 3 AM
0 3 * * * /opt/devpulse/scripts/backup-db.sh /backups
```

**Restore from backup:**

```bash
gunzip < /backups/devpulse-20260401-120000.sql.gz | docker compose -f docker-compose.yml exec -T db psql -U devpulse devpulse
```

**Retention:** backups older than 30 days are automatically deleted.

### Rollback

**Code only** (revert to previous commit):

```bash
./scripts/rollback.sh
```

**Code + database restore:**

```bash
./scripts/rollback.sh --restore-db /backups/devpulse-20260401-120000.sql.gz
```

**Permanent rollback** (triggers a clean CI/CD deploy):

```bash
git revert <commit-hash> && git push origin main
```

> `rollback.sh` leaves you on a detached HEAD. Use `git revert` for a permanent, CI/CD-tracked rollback.

### Logs

**View live logs:**

```bash
docker compose -f docker-compose.yml logs backend --tail 100 -f
docker compose -f docker-compose.yml logs frontend --tail 100 -f
```

**Log rotation** is configured: 10 MB max per file, 3 files per service.

### Monitoring (Optional)

Enable the observability stack:

```bash
docker compose -f docker-compose.yml --profile logging up -d
```

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | `http://localhost:3002` | Log visualization, pre-built "App Health" dashboard |
| Loki | `http://localhost:3100` | Log storage (90-day retention) |
| Prometheus | `http://localhost:9090` | Container metrics |
| cAdvisor | `http://localhost:8080` | Docker container resource stats |

> **Change the default Grafana password!** Default is `admin` / `devpulse` (set `GF_ADMIN_PASSWORD` in `.env`).

**Simple uptime check** (without the full stack):

```bash
# Add to crontab:
*/5 * * * * curl -sf https://<your-domain>/api/health || echo "DevPulse is down" | mail -s "Alert" ops@company.com
```

### Updates

Push to `main` → CI runs tests → auto-deploys if green. Database migrations (`alembic upgrade head`) run automatically as part of `deploy.sh` before restarting services.

---

## 9. Security Checklist

Before going live, verify each item:

- [ ] Server is on VPN / internal network only (not public internet)
- [ ] Caddy IP whitelist configured with your actual CIDR ranges
- [ ] HTTPS enabled (auto via Let's Encrypt, or internal CA cert)
- [ ] `POSTGRES_PASSWORD` changed from default (`devpulse`)
- [ ] `JWT_SECRET` is randomly generated (32+ hex chars)
- [ ] `ENCRYPTION_KEY` is set (required for Slack token storage)
- [ ] `GITHUB_WEBHOOK_SECRET` is set and matches GitHub App config
- [ ] `GF_ADMIN_PASSWORD` changed from default (if using observability stack)
- [ ] GitHub App has **read-only permissions only**
- [ ] `.env` file has `chmod 600` and lives outside the repo (`/etc/devpulse/.env`)
- [ ] `ENVIRONMENT=production` is set (disables /docs and /redoc endpoints, enables HSTS)
- [ ] DB port is localhost-only (`127.0.0.1:5432:5432` — already configured in docker-compose.yml)
- [ ] Backend port (8000) is only reachable through Caddy — use firewall rules (`ufw deny 8000` or equivalent) to block direct access, since docker-compose.yml binds it to `0.0.0.0`
- [ ] Frontend port (3001) is only reachable through Caddy — same firewall rule applies
- [ ] SSH access restricted to admin IPs
- [ ] Deploy user cannot `sudo`
- [ ] Grafana, Loki, Prometheus, and cAdvisor ports are localhost-only (already configured)

---

## 10. What NOT To Do

| Don't | Why |
|-------|-----|
| Expose to the public internet | DevPulse shows internal engineering metrics — keep it on your VPN |
| Give the GitHub App write permissions | DevPulse is read-only; write perms are unnecessary risk |
| Skip HTTPS | JWTs and session tokens flow over the wire |
| Leave default passwords | `devpulse` for PostgreSQL, `devpulse` for Grafana are public defaults |
| Run bare `docker compose up` in production | Without `-f docker-compose.yml`, the override file is auto-loaded — it runs the backend as `root`, enables hot-reload, and mounts local code into the container |
| Share a database across multiple instances | Version skew between instances causes schema conflicts |
| Run with `ENVIRONMENT=development` | Development mode exposes /docs and /redoc API documentation endpoints |

---

## Verification Checkpoints

Use these to confirm each stage is working:

| After section | Verify |
|---------------|--------|
| Section 2 (Server Setup) | `docker --version` and `caddy version` succeed; `cat /etc/devpulse/.env` shows generated secrets |
| Section 5 (CI/CD) | Push to `main` triggers the Deploy workflow in GitHub Actions |
| Section 6 (First Deploy) | `curl https://<your-domain>/api/health` returns `{"status":"ok"}` |
| Section 7 (App Setup) | Log in and see the dashboard with synced data |

---

## 11. Troubleshooting

### Backend won't start

```bash
# Check logs for the error
docker compose -f docker-compose.yml logs backend --tail 50

# Common causes:
# - Missing or invalid .env variables (JWT_SECRET, GITHUB_APP_ID, etc.)
# - github-app.pem not mounted or wrong path → check GITHUB_APP_PEM_HOST_PATH
# - Database not ready → check: docker compose -f docker-compose.yml logs db
```

### OAuth login fails

- Verify `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` match your GitHub App's OAuth settings
- Verify the callback URL in GitHub App settings is exactly `https://<your-domain>/api/auth/callback`
- Verify `FRONTEND_URL` in `.env` matches your actual domain (including `https://`)
- Check that your GitHub user is a member of the `GITHUB_ORG` organization

### Webhooks not arriving

- Verify `GITHUB_WEBHOOK_SECRET` in `.env` matches the webhook secret in your GitHub App settings
- Verify the webhook URL in GitHub App settings is `https://<your-domain>/api/webhooks/github`
- Check the webhook delivery log in GitHub App settings → Advanced → Recent Deliveries
- Ensure Caddy is proxying `/api/*` to the backend (test: `curl https://<your-domain>/api/health`)

### Caddy shows "Access denied" (403)

Your IP is not in the allowlist. Edit `/etc/caddy/Caddyfile` and add your IP/CIDR range to the `@blocked` matcher, then reload:

```bash
sudo systemctl reload caddy
```

### "Permission denied" running deploy scripts

```bash
chmod +x scripts/*.sh
```

### Database migration fails

```bash
# Check which migration is failing
docker compose -f docker-compose.yml run --rm backend alembic history --verbose

# Check current database state
docker compose -f docker-compose.yml run --rm backend alembic current

# If the database is fresh, just run all migrations
docker compose -f docker-compose.yml run --rm backend alembic upgrade head
```

### Sync fails or gets stuck

- Check backend logs: `docker compose -f docker-compose.yml logs backend --tail 100 | grep sync`
- If a sync is stuck in "started" state, use the Force Stop button in Admin → Sync, or call `POST /api/sync/force-stop`
- GitHub API rate limits: the app has built-in retry with backoff, but very large orgs may hit secondary rate limits. Check the sync detail page for specific errors.

### Container keeps restarting

```bash
# Check the exit code and logs
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml logs <service> --tail 50
```

### How to fully reset

If you need to start completely fresh (destroys all data):

```bash
cd /opt/devpulse
docker compose -f docker-compose.yml down -v   # stops containers AND deletes volumes
docker compose -f docker-compose.yml up -d db   # start fresh database
docker compose -f docker-compose.yml run --rm backend alembic upgrade head
docker compose -f docker-compose.yml up -d
```
