# Task: Add GitHub Actions Error Triage Workflow

## Status: Complete
## Depends On: adopt-error-convention.md (error classification must be implemented first)

## Context

The Nordlabs error monitoring system (Sentinel) dispatches `repository_dispatch` events
to target repos when error thresholds are crossed. A GitHub Actions workflow receives
these events, uses Claude Code to perform root cause analysis, creates GitHub issues,
and optionally opens auto-fix PRs.

**Already done (in the Claros monorepo and Sentinel repo):**
- Sentinel's `dispatch_error_triage()` sends `event_type: "error-triage"` with a
  structured `client_payload` containing error details
- Sentinel's callback API (`POST /api/v1/callback`) accepts triage results
- Auth uses HMAC-SHA256 key derivation: `HMAC(SENTINEL_SECRET, app_id)`
- Reference workflow exists at `C:\Projects\claros\.github\workflows\error-triage.yml`

## What Needs to Be Done

### 1. Create `.github/workflows/error-triage.yml`

```yaml
name: Error Triage

on:
  repository_dispatch:
    types: [error-triage]

permissions:
  contents: write
  issues: write
  pull-requests: write

concurrency:
  group: sentinel-${{ github.event.client_payload.sentinel_aggregate_id }}
  cancel-in-progress: false

jobs:
  triage:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Derive Sentinel API key
        id: sentinel-key
        env:
          APP_ID: ${{ github.event.client_payload.app_id }}
          SENTINEL_SECRET: ${{ secrets.SENTINEL_SECRET }}
        run: |
          KEY=$(echo -n "$APP_ID" | openssl dgst -sha256 -hmac "$SENTINEL_SECRET" -hex | awk '{print $NF}')
          echo "::add-mask::$KEY"
          echo "key=$KEY" >> "$GITHUB_OUTPUT"

      - uses: anthropics/claude-code-action@v1
        env:
          SENTINEL_CALLBACK_URL: ${{ github.event.client_payload.sentinel_callback_url }}
          SENTINEL_KEY: ${{ steps.sentinel-key.outputs.key }}
          SENTINEL_AGGREGATE_ID: ${{ github.event.client_payload.sentinel_aggregate_id }}
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          prompt: |
            You are triaging a production error reported by Sentinel.

            ## Error Context
            - **App**: ${{ github.event.client_payload.app_id }}
            - **Component**: ${{ github.event.client_payload.component }}
            - **Error code**: ${{ github.event.client_payload.error_code }}
            - **Message**: "${{ github.event.client_payload.error_message }}"
            - **Endpoint**: ${{ github.event.client_payload.endpoint_path }}
            - **Category**: ${{ github.event.client_payload.error_category }}
            - **Frequency**: ${{ github.event.client_payload.total_frequency }} events from ${{ github.event.client_payload.distinct_sources }} source(s)
            - **Versions affected**: ${{ github.event.client_payload.affected_versions }}
            - **First reported**: ${{ github.event.client_payload.first_reported }}
            - **Last reported**: ${{ github.event.client_payload.last_reported }}
            - **Sentinel aggregate ID**: ${{ github.event.client_payload.sentinel_aggregate_id }}

            ## Codebase Layout

            GitHub Cadency (DevPulse) — engineering intelligence dashboard.

            ```
            backend/app/
              api/              — FastAPI routers (auth, developers, stats, goals, sync, webhooks, ai_analysis, slack, notifications)
              models/           — SQLAlchemy ORM models + database.py
              schemas/          — Pydantic request/response models
              services/         — Business logic (github_sync, stats, ai_analysis, slack, notifications, work_categories, roles)
            frontend/src/
              pages/            — React pages
              components/       — UI components
            ```

            The "component" field maps to modules:
            - `api.stats` -> backend/app/api/stats.py
            - `services.github_sync` -> backend/app/services/github_sync.py

            **Stack**: Python 3.11, FastAPI, SQLAlchemy 2.0 async (asyncpg),
            PostgreSQL, React 19, Vite, Tailwind CSS v4.
            Tests: pytest + pytest-asyncio.

            **Key invariant**: GitHub Cadency is read-only — it never writes back
            to GitHub. All stats are deterministic; AI analysis is on-demand only.

            ## Your Tasks

            ### 1. Root Cause Analysis
            - Find the code that produces this error
            - Identify the root cause
            - Determine severity: P1 (sync/data broken), P2 (degraded metrics), P3 (edge case)

            ### 2. Create GitHub Issue
            ```bash
            gh issue create \
              --title "[Sentinel] <component>: <short description>" \
              --body "<body with root cause, impact, fix suggestion, aggregate ID>" \
              --label "sentinel,auto-triage,<P1|P2|P3>"
            ```

            ### 3. Auto-Fix (only if confident)
            Only for localized, mechanical, high-confidence fixes.
            Never auto-fix GitHub App auth, webhook verification, or sync logic.
            Run `cd backend && uv run pytest -x -q` before creating any PR.

            ### 4. Report Back to Sentinel

            The following environment variables are available for the callback:
            - `$SENTINEL_CALLBACK_URL` — Sentinel callback endpoint
            - `$SENTINEL_KEY` — Pre-derived HMAC auth key
            - `$SENTINEL_AGGREGATE_ID` — Aggregate ID to reference

            ```bash
            curl -s -X POST "$SENTINEL_CALLBACK_URL" \
              -H "Authorization: Bearer $SENTINEL_KEY" \
              -H "Content-Type: application/json" \
              -d "{\"aggregate_id\": \"$SENTINEL_AGGREGATE_ID\", \"action\": \"issue_created\", \"github_url\": \"<ISSUE_URL>\", \"details\": {\"title\": \"...\", \"severity\": \"...\", \"confidence\": \"...\", \"root_cause\": \"...\"}}"
            ```

          allowed_tools: "Read,Glob,Grep,Bash(git *),Bash(gh *),Bash(curl *),Bash(cd backend*),Bash(cd frontend*),Bash(uv *),Bash(ls *)"
```

### 2. Add GitHub Secrets

- `ANTHROPIC_API_KEY` — Claude API key for the triage agent
- `SENTINEL_SECRET` — Shared HMAC secret (same value as in Sentinel's env)

### 3. Register in Sentinel

```bash
curl -X POST https://sentinel.claros.no/api/v1/projects \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "github-cadency",
    "display_name": "GitHub Cadency",
    "github_repo": "anders-vedal/github-cadency",
    "github_app_subpath": null
  }'
```

### 4. Test with Manual Dispatch

```bash
gh api repos/anders-vedal/github-cadency/dispatches \
  -f event_type=error-triage \
  -f 'client_payload[app_id]=github-cadency' \
  -f 'client_payload[component]=services.github_sync' \
  -f 'client_payload[error_code]=HTTPError' \
  -f 'client_payload[error_message]=test dispatch' \
  -f 'client_payload[endpoint_path]=/api/sync' \
  -f 'client_payload[error_category]=app_bug' \
  -f 'client_payload[total_frequency]=10' \
  -f 'client_payload[distinct_sources]=1' \
  -f 'client_payload[affected_versions]=[]' \
  -f 'client_payload[sentinel_aggregate_id]=test-cadency-001' \
  -f 'client_payload[sentinel_callback_url]=https://sentinel.claros.no/api/v1/callback' \
  -f 'client_payload[app_subpath]='
```

## Definition of Done

- [x] `.github/workflows/error-triage.yml` created
- [x] `ANTHROPIC_API_KEY` and `SENTINEL_SECRET` secrets set in repo
- [x] Project registered in Sentinel (project ID: `5a17dd30-96e5-4935-8c00-44b469bc1fa3`)
- [x] Manual dispatch tested (run `24077567156` triggered successfully)
