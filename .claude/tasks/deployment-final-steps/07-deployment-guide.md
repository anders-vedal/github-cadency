# Task 7: Write Production Deployment Guide

**Status:** pending
**Blocked by:** All other tasks (Tasks 1-6) — this documents the final state

## Problem

No single document walks someone through deploying DevPulse end-to-end. The checklist file is for implementation planning; the deployment guide is for operators.

## File to Create

### `docs/DEPLOYMENT.md`

This is the human-readable guide for anyone deploying DevPulse. Structure:

### Section 1: Prerequisites

- VM: 2 CPU, 4 GB RAM minimum (AWS `t3.medium`, Azure `B2s`, GCP `e2-medium`)
- Docker Engine + Docker Compose v2
- Caddy (or nginx/Traefik) for HTTPS termination
- Server on company VPN or internal network
- GitHub org with a GitHub App (instructions below)
- SSH key pair for CI/CD deploy

### Section 2: Server Setup (one-time)

Step-by-step commands:
1. Install Docker: `curl -fsSL https://get.docker.com | sh`
2. Install Caddy: link to https://caddyserver.com/docs/install
3. Create deploy user + add to docker group
4. Create directories: `/opt/devpulse`, `/backups`, `/etc/devpulse`
5. Clone repo to `/opt/devpulse`
6. Create `/etc/devpulse/.env` → symlink to `/opt/devpulse/.env`
7. Copy `github-app.pem` with `chmod 600`
8. Configure Caddy: copy `infrastructure/Caddyfile` → edit domain + IP ranges
9. Start Caddy: `sudo systemctl enable --now caddy`

### Section 3: GitHub App Creation

Step-by-step with exact permission checkboxes:
- Repository permissions: Contents (read), Pull requests (read), Issues (read), Checks (read), Metadata (read)
- Organization permissions: Members (read)
- **No write permissions** — DevPulse is strictly read-only
- Set OAuth callback URL: `https://<your-domain>/api/auth/callback`
- Set webhook URL: `https://<your-domain>/api/webhooks/github`
- Install the app on your org → select repos
- Download private key `.pem` → save to server

### Section 4: Production `.env` Configuration

Copy `.env.example` → edit. Exact secret generation commands:
```bash
openssl rand -hex 32          # JWT_SECRET
openssl rand -hex 16          # POSTGRES_PASSWORD
openssl rand -hex 32          # GITHUB_WEBHOOK_SECRET
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ENCRYPTION_KEY
```

Table of every variable with: name, required/optional, what it does, example value.

### Section 5: CI/CD Setup

1. Generate SSH key: `ssh-keygen -t ed25519 -f deploy-key -N ""`
2. Add public key to server's `deploy` user
3. Add secrets to GitHub repo: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY`
4. Push to `main` → verify workflow runs

Note about network requirements: GitHub runners need SSH access to the server. Options if server has no public IP.

### Section 6: First Deploy

```bash
# On the server (first time only):
cd /opt/devpulse
docker compose -f docker-compose.yml up -d
```

After this, all subsequent deploys happen automatically via CI/CD on push to main.

### Section 7: First-Time App Setup

1. Open `https://<your-domain>`
2. Log in with the GitHub account set as `DEVPULSE_INITIAL_ADMIN`
3. Admin → Sync → Run first sync
4. Admin → Sync → Configure schedule
5. Admin → Team → Assign roles

### Section 8: Operations

**Backups:**
- Auto: `deploy.sh` backs up before every deploy
- Manual: `./scripts/backup-db.sh`
- Cron: `0 3 * * * /opt/devpulse/scripts/backup-db.sh /backups`
- Restore: `gunzip < /backups/devpulse-YYYYMMDD.sql.gz | docker exec -i devpulse-db-1 psql -U devpulse devpulse`

**Rollback:**
- Code only: `./scripts/rollback.sh`
- Code + DB: `./scripts/rollback.sh --restore-db /backups/devpulse-YYYYMMDD.sql.gz`
- Permanent: `git revert <commit> && git push` (triggers clean deploy)

**Logs:**
- View: `docker compose -f docker-compose.yml logs backend --tail 100 -f`
- Log rotation is configured (10MB x 3 files per service)

**Monitoring (optional):**
- Enable: `docker compose -f docker-compose.yml --profile logging up -d`
- Grafana at `localhost:3002` (change default password!)
- Simple uptime: cron `curl -sf https://<domain>/api/health`

**Updates:**
- Push to `main` → CI runs tests → auto-deploys if green
- Migrations run automatically on backend startup (Alembic `upgrade head`)

### Section 9: Security Checklist

- [ ] Server is on VPN / internal network only
- [ ] Caddy IP whitelist configured with actual CIDR ranges
- [ ] HTTPS enabled (auto via Let's Encrypt or internal CA cert)
- [ ] All default passwords changed (PostgreSQL, Grafana)
- [ ] JWT_SECRET is randomly generated (32+ chars)
- [ ] ENCRYPTION_KEY is set (required for Slack token storage)
- [ ] GitHub App has read-only permissions only
- [ ] `.env` file has `chmod 600` and lives outside the repo
- [ ] SSH access restricted to admin IPs
- [ ] Deploy user cannot `sudo`
- [ ] `ENVIRONMENT=production` is set (disables /docs and /redoc endpoints)
- [ ] DB port is localhost-only (`127.0.0.1:5432:5432`)

### Section 10: What NOT To Do

- Don't expose to public internet — internal engineering metrics
- Don't give GitHub App write permissions — DevPulse is read-only
- Don't skip HTTPS — JWTs flow over the wire
- Don't leave default passwords — `devpulse:devpulse` for PostgreSQL, `devpulse` for Grafana
- Don't run bare `docker compose up` in production — the override file enables hot-reload and runs containers as root
- Don't run local instances with a shared DB — version skew, no benefit

## Verification

The guide should be testable by following it on a fresh VM. Key checkpoints:
1. After Section 2: `docker --version` and `caddy version` work
2. After Section 5: pushing to main triggers a GitHub Actions workflow
3. After Section 6: `curl https://<domain>/api/health` returns `{"status": "ok"}`
4. After Section 7: can log in and see the dashboard
