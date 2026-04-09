# Task 6: Create GitHub Actions CI/CD Deploy Workflow

**Status:** done

## Problem

No CI/CD pipeline. Deployments are manual. The goal: push to `main` → tests pass → auto-deploy to the server.

## Files to Create

### 6a. `.github/workflows/deploy.yml`

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
    concurrency:
      group: deploy-production
      cancel-in-progress: false

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

**Key design decisions:**

- **Two jobs (`test` → `deploy`):** Tests run on GitHub's infrastructure (fast, free). Deploy only runs if tests pass. If tests fail, nothing is deployed.
- **`concurrency` group:** Prevents two deploys running simultaneously if you push twice quickly. `cancel-in-progress: false` means the first deploy finishes rather than being killed.
- **`git pull` in the SSH step:** The server's repo is updated before `deploy.sh` runs. `deploy.sh` itself doesn't pull (it's designed to work from the current checkout).
- **`appleboy/ssh-action`:** Well-maintained action (~14k stars) for running commands over SSH. Alternative: `webfactory/ssh-agent` + raw `ssh` commands, but more boilerplate.
- **Frontend `pnpm build` in test job:** Catches TypeScript errors and build failures before deploy. The actual production build happens inside Docker on the server.

### 6b. Required GitHub Actions Secrets

Set in repo **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value | How to get it |
|--------|-------|---------------|
| `DEPLOY_HOST` | Server IP or hostname | e.g., `10.0.1.50` or `devpulse.internal.company.com` |
| `DEPLOY_USER` | SSH username on server | e.g., `deploy` |
| `DEPLOY_KEY` | SSH private key (full file contents) | Generate with `ssh-keygen -t ed25519 -f deploy-key -N ""`, paste contents of `deploy-key` (not `.pub`) |

**Important:** The `DEPLOY_HOST` must be reachable from GitHub's runners. If the server is behind a VPN with no public IP, you'll need one of:
- A bastion/jump host with a public IP that can reach the internal server
- A self-hosted GitHub Actions runner inside your network
- A VPN client on the runner (more complex)

For most setups, the server has a public IP but Caddy's IP whitelist blocks non-VPN traffic. GitHub Actions connects via SSH (port 22), which bypasses Caddy entirely since SSH != HTTP.

### 6c. Server-Side SSH Setup

Run these on the deploy server (one-time):

```bash
# 1. Create a deploy user with Docker access
sudo adduser --disabled-password --gecos 'DevPulse Deploy' deploy
sudo usermod -aG docker deploy

# 2. Add the deploy public key
sudo mkdir -p /home/deploy/.ssh
# Paste your deploy-key.pub contents:
echo "ssh-ed25519 AAAA... deploy-ci" | sudo tee /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys

# 3. Ensure deploy user owns the app directory
sudo mkdir -p /opt/devpulse /backups
sudo chown -R deploy:deploy /opt/devpulse /backups

# 4. Clone the repo (first time only)
sudo -u deploy git clone <repo-url> /opt/devpulse

# 5. Symlink production .env
sudo mkdir -p /etc/devpulse
# Create and edit /etc/devpulse/.env with production values
sudo ln -sf /etc/devpulse/.env /opt/devpulse/.env
sudo chown deploy:deploy /etc/devpulse/.env
sudo chmod 600 /etc/devpulse/.env
```

**Why a dedicated `deploy` user:**
- Principle of least privilege — the CI key can only run Docker commands, not `sudo`
- If the key is compromised, blast radius is limited to the app
- Audit trail: `deploy` user's actions are logged separately

**Why `/etc/devpulse/.env` (secrets outside the repo):**
- `git pull` never touches the `.env` file
- No risk of accidentally committing secrets
- Symlink makes it transparent to Docker Compose

## Flow Diagram

```
Push to main
    ↓
[test job]
    ├─ Install Python deps → Run pytest
    └─ Install Node/pnpm → Run pnpm build
    ↓ (both pass)
[deploy job]
    ├─ SSH into server
    ├─ git pull origin main
    └─ ./scripts/deploy.sh
        ├─ Backup DB (if running)
        ├─ docker compose build
        ├─ docker compose up -d
        └─ Health check (curl /api/health)
    ↓
Deploy complete (visible in GitHub Actions UI)
```

## Verification

```bash
# 1. Set up secrets in GitHub
# Go to repo → Settings → Secrets → Add DEPLOY_HOST, DEPLOY_USER, DEPLOY_KEY

# 2. Push a test commit to main
git commit --allow-empty -m "test: verify CI/CD pipeline"
git push origin main

# 3. Watch the workflow
# Go to repo → Actions → "Deploy" workflow
# test job should run first, then deploy job

# 4. Verify on server
ssh deploy@<server> "docker compose -f /opt/devpulse/docker-compose.yml ps"
```
