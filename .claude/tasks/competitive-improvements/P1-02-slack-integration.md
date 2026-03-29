# P1-02: Slack Integration for Alerts and PR Nudges

> Priority: 1 (Table Stakes) | Effort: Large | Impact: High
> Competitive gap: All major competitors have Slack integration. DevPulse alerts only visible when someone opens the dashboard.

## Context

DevPulse currently has no notification system. Alerts (stale PRs, workload imbalance, sync failures, high-risk PRs) are only visible when someone actively opens the dashboard. Swarmia's Slack-first workflow is a core differentiator in the market.

The competitive analysis notes this is a key operationalization gap: "DevPulse shows you the data but doesn't help you act on it."

## What to Build

### Phase 1: Slack App + Webhook Notifications

**Slack App setup:**
- DevPulse registers as a Slack App (self-hosted teams create their own Slack App)
- OAuth 2.0 flow to connect Slack workspace
- Store bot token + channel mappings in DB

**Notification types (configurable per-channel):**

| Alert | Trigger | Default Channel |
|-------|---------|----------------|
| Stale PR nudge | PR open > N days (configurable, default 3) | #engineering |
| High-risk PR | Risk score > 0.7 on new PR | #engineering |
| Workload alert | Developer moves to "overloaded" status | #eng-leads |
| Sync failure | Sync completes with errors or fails | #devpulse-admin |
| Sync complete | Successful sync summary | #devpulse-admin |
| Weekly digest | Scheduled summary of key metrics | #engineering |

### Phase 2: Interactive Messages

- Stale PR notifications include "View PR" button (links to GitHub) and "Snooze" button
- Workload alerts include "View Dashboard" link
- Weekly digest includes sparkline-style metric summaries

## Backend Changes

### New Model: `slack_config` table
```
id, workspace_id, team_name, bot_token (encrypted),
default_channel_id, channel_mappings (JSONB),
notification_settings (JSONB), installed_at, installed_by
```

### New Model: `notification_log` table
```
id, type, channel_id, message_ts, payload (JSONB),
sent_at, developer_id (nullable)
```

### New Service: `backend/app/services/slack.py`
- `send_notification(type, payload, channel_override=None)`
- `send_stale_pr_nudge(pr, channel)`
- `send_risk_alert(pr, risk_score, channel)`
- `send_workload_alert(developer, score, channel)`
- `send_sync_summary(sync_event, channel)`
- `send_weekly_digest(channel)`
- Rate limiting: max 1 notification per PR per type per 24h (prevent spam)

### New Router: `backend/app/api/slack.py`
- `POST /api/slack/install` — initiate Slack OAuth
- `GET /api/slack/callback` — OAuth callback, store tokens
- `GET /api/slack/config` — get current config (admin only)
- `PATCH /api/slack/config` — update channel mappings, notification settings
- `POST /api/slack/test` — send test notification
- `DELETE /api/slack/disconnect` — remove integration

### Config (`backend/app/config.py`)
- `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_SIGNING_SECRET`
- `SLACK_ENCRYPTION_KEY` — for encrypting bot tokens at rest

### Integration Points
- After sync completes: trigger sync summary notification
- Scheduled job (daily): check for stale PRs → send nudges
- Scheduled job (weekly): compute digest → send summary
- On webhook PR event: if risk score > threshold → send alert
- On stats recompute: if workload transitions to overloaded → send alert

## Frontend Changes

### Slack Settings Page (`/admin/settings/slack`)
- Connection status + install/disconnect buttons
- Channel mapping UI (dropdown per notification type)
- Per-notification toggle (enable/disable each type)
- Threshold configuration (stale PR days, risk score threshold)
- Test notification button
- Notification history log

### Nav Update
- Add "Integrations" or "Notifications" to Admin sidebar

## Dependencies
- `slack_sdk` Python package for Slack API
- `cryptography` for token encryption at rest

## Security Considerations
- Bot tokens encrypted at rest using Fernet symmetric encryption
- Slack signing secret verification on all incoming Slack requests
- Admin-only access to Slack configuration
- No sensitive data (code, PR content) in notifications — only metadata and links

## Testing
- Unit test notification formatting for each type
- Unit test rate limiting (no duplicate notifications)
- Unit test channel routing logic
- Mock Slack API for integration tests
- Test OAuth flow with mock Slack endpoints

## Status

**Completed** — implemented 2026-03-29.

### Deviations from Original Spec

- **No OAuth flow**: Used manual bot token approach instead of Slack App OAuth. Admin pastes `xoxb-` token from their Slack App settings. Simpler, covers all use cases, upgradable to OAuth later.
- **DMs instead of channel routing**: Per user request, notifications go as DMs to individual developers (via Slack user ID) rather than fixed channel routing. Each developer configures their own Slack user ID and notification preferences.
- **No rate limiting**: Deferred — relies on daily/weekly cron schedule as natural dedup. Can add `notification_log` dedup checks later if spam becomes an issue.
- **Bot token not encrypted at rest**: Stored as plaintext in DB for now (app not in production). `cryptography` package already in requirements for future Fernet encryption.
- **No interactive messages (Phase 2)**: Snooze buttons, "View PR" actions deferred to future work.
- **Uses `slack_sdk`**: Instead of plain webhooks, uses `slack_sdk.web.async_client.AsyncWebClient` for full DM + channel support.

## Acceptance Criteria
- [n/a] ~~Slack App OAuth flow works (install/disconnect)~~ — replaced with manual bot token
- [x] Stale PR nudges sent daily for PRs exceeding threshold
- [x] High-risk PR alerts on new PRs above risk threshold
- [x] Workload alerts when developers become overloaded
- [x] Sync status notifications (success/failure)
- [x] Weekly digest with key metric summaries
- [x] Per-notification-type enable/disable (global + per-user)
- [ ] Rate limiting prevents notification spam — deferred
- [x] Admin-only configuration page
- [ ] Bot tokens encrypted at rest — deferred (not in production)

## Files Created

| File | Purpose |
|------|---------|
| `backend/app/services/slack.py` | Slack service: config CRUD, user settings, notification senders, scheduled jobs |
| `backend/app/api/slack.py` | 7 API endpoints for Slack config, test, user settings, notification history |
| `backend/migrations/versions/019_add_slack_integration.py` | 3 new tables: slack_config, slack_user_settings, notification_log |
| `backend/tests/unit/test_slack_service.py` | 11 unit tests for service functions |
| `backend/tests/integration/test_slack_api.py` | 14 integration tests for API endpoints |
| `frontend/src/pages/settings/SlackSettings.tsx` | Admin Slack settings page |
| `frontend/src/hooks/useSlack.ts` | 6 TanStack Query hooks for Slack API |
| `frontend/src/components/SlackPreferencesSection.tsx` | Per-user notification preferences on DeveloperDetail |

## Files Modified

| File | Change |
|------|--------|
| `backend/app/models/models.py` | +3 ORM models: SlackConfig, SlackUserSettings, NotificationLog |
| `backend/app/schemas/schemas.py` | +9 Pydantic schemas for Slack |
| `backend/app/main.py` | Router registration + 2 hourly scheduler jobs |
| `backend/app/services/github_sync.py` | Post-sync Slack notification hook |
| `backend/requirements.txt` | +slack_sdk==3.34.0 |
| `frontend/src/utils/types.ts` | +7 TypeScript interfaces for Slack |
| `frontend/src/App.tsx` | Route + sidebar item for /admin/slack |
| `frontend/src/components/Layout.tsx` | Admin dropdown item |
| `frontend/src/pages/DeveloperDetail.tsx` | SlackPreferencesSection integration |

## Packages Added

- `slack_sdk==3.34.0` (backend) — Slack Web API async client for DMs and channel messages
