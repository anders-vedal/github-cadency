# Hetzner Cloud Server Setup

Multi-app server setup guide for hosting DevPulse and other applications on a single Hetzner Cloud server. Complete this guide once, then follow per-app deployment guides (e.g., `DEPLOYMENT.md` for DevPulse).

---

## 1. Create a Hetzner Account

1. Go to **https://accounts.hetzner.com/signUp**
2. Register with your email and verify it
3. Complete identity verification (Hetzner may request ID upload or a small payment verification)
4. Once verified, go to **https://console.hetzner.cloud** — this is your management dashboard

---

## 2. Add Your SSH Key

Before creating a server, add your SSH public key to Hetzner.

If you don't have one yet, generate it on your local machine:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/hetzner -N ""
```

In the Hetzner Cloud Console:

1. Go to **Security > SSH Keys** in the left sidebar
2. Click **Add SSH Key**
3. Paste the contents of `~/.ssh/hetzner.pub`
4. Name it (e.g., `my-laptop`)

---

## 3. Create a Firewall

In the Hetzner Cloud Console, go to **Security > Firewalls** and create a firewall called `apps-fw`.

### Inbound rules

| Rule name | Protocol | Port | Source |
|-----------|----------|------|--------|
| SSH | TCP | 22 | Your IP (`x.x.x.x/32`) or `0.0.0.0/0` if you connect from varying IPs |
| HTTP | TCP | 80 | `0.0.0.0/0` and `::/0` |
| HTTPS | TCP | 443 | `0.0.0.0/0` and `::/0` |
| Ping | ICMP | — | `0.0.0.0/0` and `::/0` |

Do **not** expose any application ports (8000, 3001, 5432, etc.). All traffic goes through Caddy on 80/443.

---

## 4. Create the Server

In the Hetzner Cloud Console, click **+ Create Server**.

| Setting | Value |
|---------|-------|
| **Location** | Pick closest to your team. EU: Falkenstein (fsn1), Nuremberg (nbg1), Helsinki (hel1). US: Ashburn (ash), Hillsboro (hil) |
| **Image** | **Ubuntu 24.04** |
| **Type** | See sizing table below |
| **SSH Key** | Select the key you added in step 2 |
| **Firewall** | Select `apps-fw` from step 3 |
| **Name** | `apps` (or whatever you prefer) |

### Server sizing

Pick based on total workload across all apps:

| Server type | vCPUs | RAM | Disk | Monthly price | Use case |
|-------------|-------|-----|------|--------------|----------|
| CX32 | 4 | 8 GB | 80 GB | ~€10.49/mo | 2-3 lightweight apps, tight budget |
| **CX42** | **8** | **16 GB** | **160 GB** | **~€19.49/mo** | **Recommended: 3+ apps including a monolith** |
| CX52 | 16 | 32 GB | 240 GB | ~€38.49/mo | Heavy monolith or many apps |

**CX42 is recommended** for hosting DevPulse + a recruitment platform + a 7-app monolith (Claros) with room to grow.

You can resize up or down later in the Hetzner console (requires a brief reboot, no data loss).

After creation, note the **public IPv4 address** (e.g., `204.168.229.167`).

### Pricing reference

Check current prices at **https://www.hetzner.com/cloud/** — the prices above are approximate as of early 2026.

---

## 5. DNS Setup

Point subdomains at your server's IP. Go to your DNS provider (Cloudflare, Namecheap, Route53, etc.) and add **A records**:

```
devpulse.yourdomain.com    A    65.108.x.x
recruit.yourdomain.com     A    65.108.x.x
claros.yourdomain.com      A    65.108.x.x
```

Add more records as you add apps. Each app gets its own subdomain.

**Alternative — wildcard record:**

```
*.yourdomain.com    A    65.108.x.x
```

This covers all future subdomains automatically. However, Caddy still needs each domain listed explicitly in the Caddyfile to provision its TLS certificate (wildcard certs require DNS challenge configuration, which is more complex). Individual A records + individual Caddy blocks is the simpler path.

---

## 6. Server Setup (One-Time)

SSH into the server:

```bash
ssh -i ~/.ssh/hetzner root@204.168.229.167
```

### Automated setup (recommended)

DevPulse includes a bootstrap script that installs Docker, Caddy, creates the deploy user, and sets up all directories in one command.

**Step 1 — Generate a deploy SSH key** on your local machine (separate from your personal key):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N ""
cat ~/.ssh/deploy_key.pub    # copy this output
```

**Step 2 — Upload and run the bootstrap script** on the server:

```bash
# Upload the script (before cloning the repo)
scp -i ~/.ssh/hetzner scripts/server-bootstrap.sh root@65.108.x.x:/root/

# SSH in and run it
ssh -i ~/.ssh/hetzner root@65.108.x.x

# Run with all your app names and the deploy public key:
EXTRA_APPS="recruitment claros" ./server-bootstrap.sh "ssh-ed25519 AAAA... deploy-ci"
```

This installs Docker + Caddy, creates the `deploy` user (with Docker access), creates `/opt/<app>`, `/etc/<app>`, and `/backups` for each app, adds the deploy SSH key, and pre-creates `.pem` placeholder files with correct permissions.

**Step 3 — Clone repos** as the deploy user:

```bash
su - deploy
git clone <devpulse-repo-url> /opt/devpulse
# Repeat for other apps:
# git clone <recruitment-repo-url> /opt/recruitment
# git clone <claros-repo-url> /opt/claros
exit
```

The private key (`~/.ssh/deploy_key`) is used as a GitHub Actions secret. The same key works for all apps since they all deploy as the `deploy` user.

### Manual setup (alternative)

If you prefer to run each step manually, see the bootstrap script source (`scripts/server-bootstrap.sh`) — it documents each step with comments. The script installs Docker, Caddy, creates the `deploy` user, creates all directories, and configures the deploy SSH key.

---

## 7. Caddy Configuration (Multi-App)

Caddy serves as the single reverse proxy for all apps. It handles HTTPS termination (auto Let's Encrypt), routing, and optional IP whitelisting.

Edit the Caddyfile:

```bash
nano /etc/caddy/Caddyfile
```

### Example Caddyfile for three apps

```
# ============================================================
# DevPulse — engineering intelligence dashboard
# Backend: localhost:8000, Frontend: localhost:3001
# ============================================================
devpulse.yourdomain.com {
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle {
        reverse_proxy localhost:3001
    }
}

# ============================================================
# Recruitment platform
# Adjust ports to match your app's docker-compose.yml
# ============================================================
recruit.yourdomain.com {
    reverse_proxy localhost:4000
}

# ============================================================
# Claros — 7-app monolith
# Option A: single entrypoint (if Claros has its own router)
# ============================================================
claros.yourdomain.com {
    reverse_proxy localhost:5000
}

# Option B: if each Claros app needs its own subdomain
# app1.claros.yourdomain.com {
#     reverse_proxy localhost:5001
# }
# app2.claros.yourdomain.com {
#     reverse_proxy localhost:5002
# }
```

### Adding IP whitelisting (optional, per-app)

Add inside any site block to restrict access:

```
    @blocked not remote_ip 10.0.0.0/8 192.168.0.0/16 YOUR.OFFICE.IP/32
    respond @blocked "Access denied" 403
```

### TLS

If your subdomains have public DNS A records, Caddy auto-provisions Let's Encrypt certificates with zero configuration. For internal-only domains:

```
    # Inside the site block:
    tls /etc/caddy/certs/your-cert.pem /etc/caddy/certs/your-key.pem

    # Or self-signed (testing only):
    tls internal
```

### Start Caddy

```bash
systemctl enable --now caddy
```

After editing the Caddyfile later:

```bash
systemctl reload caddy
```

---

## 8. Port Allocation

Each app must use unique host ports. Caddy routes external traffic; these ports are internal only.

| Port range | App | Services |
|------------|-----|----------|
| 8000, 3001, 5433 | DevPulse | Backend, frontend, PostgreSQL |
| 4000-4099 | Recruitment | Adjust in its docker-compose.yml |
| 5000-5099 | Claros | Adjust in its docker-compose.yml |
| 6000-6099 | (Future app) | Reserve as needed |

**Rules:**
- Never expose database ports externally — bind to `127.0.0.1` (e.g., `127.0.0.1:5433:5432`)
- Only ports 80 and 443 (Caddy) are reachable from outside the server
- Document your port assignments here or in a shared spreadsheet to avoid collisions

---

## 9. Shared vs Separate Databases

### Option A: one PostgreSQL, multiple databases (recommended to start)

Run a single `postgres:15` container and create a database per app. Less memory overhead (~150 MB for one Postgres vs ~450 MB for three).

One app's `docker-compose.yml` owns the shared Postgres container (or create a separate `docker-compose.infra.yml`). Other apps connect to it via Docker network or localhost port.

**Risk:** one app's heavy queries can affect others. If this becomes a problem, split later.

### Option B: separate PostgreSQL per app (isolated)

Each app's `docker-compose.yml` runs its own Postgres on a different host port. DevPulse already uses `127.0.0.1:5433:5432`; others would use `5434`, `5435`, etc.

More memory, but complete isolation. This is what DevPulse is configured for by default.

**For simplicity, start with Option B** (each app is self-contained) and consolidate later if memory is tight.

---

## 10. CI/CD (Per-App)

Each app repo gets its own GitHub Actions workflow. They all share the same deploy key and server.

### GitHub Actions secrets (same for all repos)

Go to each repo's **Settings > Secrets and variables > Actions** at:
`https://github.com/YOUR-USER/REPO-NAME/settings/secrets/actions`

| Secret | Value |
|--------|-------|
| `DEPLOY_HOST` | Your server IP (e.g., `65.108.x.x`) |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_KEY` | Contents of `~/.ssh/deploy_key` (the private key from step 6e) |

### Workflow template

Each app's deploy workflow SSHs to the server and runs its deploy script. The only difference is the directory:

```yaml
# .github/workflows/deploy.yml
- name: Deploy via SSH
  uses: appleboy/ssh-action@v1
  with:
    host: ${{ secrets.DEPLOY_HOST }}
    username: ${{ secrets.DEPLOY_USER }}
    key: ${{ secrets.DEPLOY_KEY }}
    script: |
      cd /opt/<app-name>       # ← only this line changes per app
      git pull origin main
      ./scripts/deploy.sh
```

DevPulse already has this workflow at `.github/workflows/deploy.yml`.

---

## 11. Adding a New App (Checklist)

When you add another application to the server:

1. **DNS:** add an A record for `newapp.yourdomain.com` pointing to the server IP
2. **Server directories:** `mkdir -p /opt/newapp /etc/newapp && chown deploy:deploy /opt/newapp /etc/newapp`
3. **Clone:** `su - deploy && git clone <repo-url> /opt/newapp`
4. **Config:** create `/etc/newapp/.env`, symlink into `/opt/newapp/.env`
5. **Ports:** pick unused ports, update the app's `docker-compose.yml`
6. **Caddy:** add a new site block to `/etc/caddy/Caddyfile`, then `systemctl reload caddy`
7. **CI/CD:** add `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY` secrets to the new repo
8. **Deploy:** `cd /opt/newapp && docker compose up -d`
9. **Backups:** add a cron job for the new app's database (if applicable)

---

## 12. Server Layout Reference

```
/opt/                          # Application code (git repos)
├── devpulse/
│   ├── docker-compose.yml
│   ├── .env → /etc/devpulse/.env
│   └── scripts/
├── recruitment/
│   ├── docker-compose.yml
│   └── .env → /etc/recruitment/.env
└── claros/
    ├── docker-compose.yml
    └── .env → /etc/claros/.env

/etc/                          # Secrets and config (outside repos)
├── caddy/
│   └── Caddyfile              # Single file, all domains
├── devpulse/
│   ├── .env                   # chmod 600
│   └── github-app.pem         # chmod 600
├── recruitment/
│   └── .env
└── claros/
    └── .env

/backups/                      # Database backups
├── devpulse-20260402-030000.sql.gz
├── recruitment-20260402-030000.sql.gz
└── claros-20260402-030000.sql.gz
```

---

## 13. Operations

### Monitoring server resources

```bash
# Live resource usage
htop

# Docker container stats
docker stats

# Disk usage
df -h
```

### Resizing the server

If you outgrow the current server type:

1. Go to **https://console.hetzner.cloud** → click your server → **Rescale**
2. Pick a larger type (e.g., CX42 → CX52)
3. Confirm — the server reboots briefly, no data is lost
4. All containers auto-restart (they have `restart: unless-stopped`)

### Backups

Set up daily cron jobs for each app's database. As the `deploy` user:

```bash
crontab -e
```

```
# DevPulse — daily at 3:00 AM
0 3 * * * /opt/devpulse/scripts/backup-db.sh /backups

# Recruitment — daily at 3:15 AM
15 3 * * * /opt/recruitment/scripts/backup-db.sh /backups

# Claros — daily at 3:30 AM
30 3 * * * /opt/claros/scripts/backup-db.sh /backups
```

### Viewing logs

```bash
# DevPulse
cd /opt/devpulse && docker compose -f docker-compose.yml logs backend --tail 100 -f

# Any app's containers
cd /opt/<app> && docker compose -f docker-compose.yml logs --tail 100 -f

# Caddy logs
journalctl -u caddy -f
```

---

## 14. Security Checklist

Before going live with any app:

- [ ] Hetzner firewall attached — only ports 22, 80, 443 open
- [ ] SSH key auth only (password auth disabled — Hetzner does this by default when you add an SSH key)
- [ ] Deploy user cannot `sudo`
- [ ] All `.env` files have `chmod 600` and live in `/etc/<app>/` (outside repos)
- [ ] No database ports exposed externally (bound to `127.0.0.1`)
- [ ] No application ports exposed externally (only reachable via Caddy)
- [ ] Caddy HTTPS enabled (auto via Let's Encrypt, or internal CA cert)
- [ ] Default passwords changed (PostgreSQL, Grafana, etc.)
- [ ] IP whitelist configured in Caddy if apps should not be publicly accessible
