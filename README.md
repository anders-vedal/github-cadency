# DevPulse

Engineering intelligence dashboard that tracks developer activity across GitHub repositories for an organization. Provides PR/review/cycle-time metrics, team benchmarks, trend analysis, workload balance, collaboration insights, developer goals, and optional on-demand AI analysis via Claude API.

## How It Works

DevPulse connects to your GitHub organization as a **read-only GitHub App**. It syncs PR, review, and issue data into a local PostgreSQL database, then computes metrics deterministically from that cached data. AI analysis (powered by Claude) is optional and off by default.

```
React Frontend (Vite :5173)  ──/api proxy──>  FastAPI Backend (:8000)  ──>  PostgreSQL (:5432)
                                                     |
                                              GitHub REST API (read-only)
                                                     |
                                              Claude API (on-demand, optional)
```

## Prerequisites

- **Docker & Docker Compose** (recommended) — or for local dev:
  - Python 3.11+
  - Node.js 20+
  - pnpm
  - PostgreSQL 15+
- A **GitHub App** configured for your organization (see below)
- An **Anthropic API key** (only if you want AI analysis features)

---

## 1. Create a GitHub App

DevPulse authenticates with GitHub via a GitHub App, not a personal access token. You need to create one:

1. Go to **GitHub > Settings > Developer settings > GitHub Apps > New GitHub App**
   - Or for an org: `https://github.com/organizations/<YOUR_ORG>/settings/apps/new`

2. Fill in the basics:
   - **Name:** Something like `DevPulse` or `DevPulse-<your-org>`
   - **Homepage URL:** `http://localhost:5173` (or your deployment URL)
   - **Webhook URL:** `https://<YOUR_PUBLIC_URL>/api/webhooks/github` (needs to be publicly accessible; use a tool like [smee.io](https://smee.io) or [ngrok](https://ngrok.com) for local development)
   - **Webhook secret:** Generate a random string (e.g., `openssl rand -hex 32`) — save this, you'll need it for `GITHUB_WEBHOOK_SECRET`

3. Set **permissions** (all read-only):
   - **Repository permissions:**
     - Contents: Read-only
     - Pull requests: Read-only
     - Issues: Read-only
     - Metadata: Read-only
   - **Organization permissions:**
     - Members: Read-only

4. Subscribe to **webhook events:**
   - `pull_request`
   - `pull_request_review`
   - `pull_request_review_comment`
   - `issues`
   - `issue_comment`
   - Do **NOT** subscribe to `push`

5. After creating the app, note these values (you'll need them for your `.env`):
   - **App ID** — shown on the app's settings page (a numeric ID)
   - **Installation ID** — install the app on your org, then find the installation ID in the URL: `https://github.com/settings/installations/<INSTALLATION_ID>`

6. Generate a **private key:**
   - On the app settings page, scroll to "Private keys" and click "Generate a private key"
   - A `.pem` file will download — save it to the project root as `github-app.pem` (or wherever you configure `GITHUB_APP_PRIVATE_KEY_PATH` to point)

---

## 2. Set Up Environment Variables

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Database — no changes needed if using Docker Compose
DATABASE_URL=postgresql+asyncpg://devpulse:devpulse@localhost:5432/devpulse

# GitHub App — from step 1 above
GITHUB_APP_ID=12345                              # Your GitHub App's numeric ID
GITHUB_APP_PRIVATE_KEY_PATH=./github-app.pem     # Path to the .pem file you downloaded
GITHUB_APP_INSTALLATION_ID=67890                 # Installation ID from the URL after installing the app
GITHUB_WEBHOOK_SECRET=whsec_your-webhook-secret  # The webhook secret you generated
GITHUB_ORG=your-org-name                         # Your GitHub organization name (e.g., "my-company")

# Auth — used to protect all API endpoints
DEVPULSE_ADMIN_TOKEN=some-secure-random-string   # Generate with: openssl rand -hex 32

# AI (optional) — only needed for AI analysis, 1:1 prep, and team health features
ANTHROPIC_API_KEY=sk-ant-...                     # Get from https://console.anthropic.com/settings/keys

# Sync scheduling (optional, defaults shown)
SYNC_INTERVAL_MINUTES=15                         # How often incremental sync runs (minutes)
FULL_SYNC_CRON_HOUR=2                            # Hour (UTC) for nightly full sync
```

### Where to find each value

| Variable | Where to find it |
|----------|-----------------|
| `GITHUB_APP_ID` | GitHub App settings page > "App ID" (top of the page) |
| `GITHUB_APP_PRIVATE_KEY_PATH` | The `.pem` file downloaded when you generated a private key for the app. Place it in the project root or specify an absolute path. |
| `GITHUB_APP_INSTALLATION_ID` | Install the app on your org, then check the URL: `github.com/settings/installations/<THIS_NUMBER>` |
| `GITHUB_WEBHOOK_SECRET` | The secret you chose when creating the app's webhook configuration |
| `GITHUB_ORG` | Your GitHub organization's login name (the one in the URL: `github.com/<THIS>`) |
| `DEVPULSE_ADMIN_TOKEN` | You create this yourself. Any random string — used as the Bearer token for all API requests. Generate one with `openssl rand -hex 32`. |
| `ANTHROPIC_API_KEY` | [Anthropic Console](https://console.anthropic.com/settings/keys) > API Keys > Create Key |

### Important notes

- The `.env` file is loaded by both the backend (via pydantic-settings) and Docker Compose (`env_file` directive)
- When running with Docker Compose, `DATABASE_URL` is overridden in `docker-compose.yml` to use the `db` service hostname — you don't need to change it
- The `github-app.pem` file must be accessible from the backend container. The default Docker Compose config mounts `./backend` into the container, so placing the `.pem` in `./backend/` and setting `GITHUB_APP_PRIVATE_KEY_PATH=./github-app.pem` will work. Alternatively, place it at the project root and use an absolute path or adjust the volume mount.
- **Never commit** `.env` or `github-app.pem` to version control

---

## 3. Running with Docker (Recommended)

```bash
docker compose up
```

This starts three services:

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://localhost:5173 | React dashboard (proxies `/api` to backend) |
| **Backend** | http://localhost:8000 | FastAPI server with auto-reload |
| **Database** | localhost:5433 | PostgreSQL 15 (user/pass/db: `devpulse`) |

The backend automatically runs Alembic migrations on startup and begins syncing on schedule.

To stop: `Ctrl+C` or `docker compose down`

To reset the database: `docker compose down -v` (removes the PostgreSQL volume)

---

## 4. Running Locally (Without Docker)

### Database

Install and start PostgreSQL 15+, then create the database:

```bash
createdb devpulse
# Or with psql:
psql -c "CREATE USER devpulse WITH PASSWORD 'devpulse';"
psql -c "CREATE DATABASE devpulse OWNER devpulse;"
```

### Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head          # Run database migrations
uvicorn app.main:app --reload # Start the API server on :8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev                      # Start the dev server on :5173
```

---

## 5. Initial Setup After First Run

1. **Add the admin token to the frontend:** Open the dashboard at http://localhost:5173 and enter your `DEVPULSE_ADMIN_TOKEN` when prompted (stored in `localStorage`).

2. **Check repo sync:** Navigate to the Sync Status page. Your organization's repositories should appear. Toggle tracking on for the repos you want to monitor.

3. **Trigger an initial sync:** Click "Full Sync" on the Sync Status page, or call the API directly:
   ```bash
   curl -X POST http://localhost:8000/api/sync/start \
     -H "Authorization: Bearer <YOUR_DEVPULSE_ADMIN_TOKEN>"
   ```

4. **Register developers:** Add team members on the Team Registry page so their GitHub usernames are linked to DevPulse profiles. PRs from unregistered contributors will still be synced but won't be attributed to a team member.

---

## 6. Webhook Setup for Real-Time Updates

For real-time PR/review/issue updates (instead of waiting for the sync interval), your GitHub App's webhook URL must be reachable from the internet.

**For local development**, use a tunneling tool:

```bash
# Using smee.io (recommended for GitHub webhooks)
npx smee-client --url https://smee.io/<YOUR_CHANNEL> --target http://localhost:8000/api/webhooks/github

# Or using ngrok
ngrok http 8000
# Then update your GitHub App's webhook URL to the ngrok URL + /api/webhooks/github
```

**For production**, point the webhook URL to your deployed backend at `https://<YOUR_DOMAIN>/api/webhooks/github`.

---

## Running Tests

```bash
cd backend
pip install -r requirements-test.txt
python -m pytest                    # All tests
python -m pytest tests/unit/        # Unit tests only
```

Tests use SQLite in-memory (via aiosqlite) — no PostgreSQL needed.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic |
| Database | PostgreSQL 15 (async via asyncpg) |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui, TanStack Query v5 |
| GitHub Integration | REST API via httpx, GitHub App auth (JWT + installation tokens) |
| AI | Anthropic Claude API (optional, on-demand only) |
| Scheduling | APScheduler (in-process) |

---

## Project Structure

```
devpulse/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── models/       # SQLAlchemy ORM models + database setup
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Business logic (sync, stats, goals, AI)
│   │   ├── config.py     # Environment variable definitions
│   │   └── main.py       # App factory, middleware, scheduler
│   ├── migrations/       # Database migrations (Alembic)
│   ├── tests/            # pytest test suite
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/        # Route components
│   │   ├── components/   # UI components (shadcn/ui + custom)
│   │   ├── hooks/        # TanStack Query hooks
│   │   └── utils/        # API client, types
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example          # Template for environment variables
└── CLAUDE.md             # AI assistant context file
```
