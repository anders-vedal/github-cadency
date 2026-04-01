# Task L-03: Migrate All Backend Loggers to Structlog

## Status
completed

## Blocked By
- L-01, L-02

## Blocks
- L-06

## Description
Replace all `import logging` / `logging.getLogger(__name__)` usage across the backend with `from app.logging import get_logger`. Add `event_type` fields to log calls for Loki label-based filtering. Preserve all existing log semantics — this is a 1:1 migration, not a behavior change.

## Files to Migrate (8 files, ~60 log calls)

- [ ] **backend/app/main.py** — 7 info, 6 warning, 1 error. Replace `logger = logging.getLogger(__name__)` with `logger = get_logger(__name__)`. Add `event_type="system.startup"` / `"system.shutdown"` / `"system.scheduler"` / `"system.sync"` as appropriate.
- [ ] **backend/app/config.py** — 1 warning (JWT secret). `event_type="system.config"`
- [ ] **backend/app/services/github_sync.py** — 4 info, 16 warning. The heaviest file. Replace module-level logger. Also update `SyncContext.sync_logger` default factory. Add `event_type="system.sync"` to sync lifecycle logs, `event_type="system.github_api"` to rate limit / API logs.
  - **Do NOT change `_add_log()`**: The JSONB `log_summary` system is user-facing and serves a different purpose. It stays as-is.
- [ ] **backend/app/services/ai_analysis.py** — Replace logger. `event_type="ai.analysis"`
- [ ] **backend/app/services/ai_settings.py** — Replace logger. `event_type="ai.settings"`
- [ ] **backend/app/services/slack.py** — 2 info, 3 warning, 2 error. `event_type="system.slack"`
- [ ] **backend/app/services/work_category.py** — 1 warning, 1 exception. `event_type="ai.categorization"`
- [ ] **backend/app/api/webhooks.py** — 1 exception. `event_type="system.webhook"`

## Migration Pattern

**Before:**
```python
import logging
logger = logging.getLogger(__name__)
logger.warning("Rate limit exhausted, waiting %ds", wait)
```

**After:**
```python
from app.logging import get_logger
logger = get_logger(__name__)
logger.warning("Rate limit exhausted", wait_seconds=wait, event_type="system.github_api")
```

Key changes:
- Replace `%s`/`%d` format strings with **keyword arguments** (structlog's structured approach)
- Add `event_type` to every log call for Loki filtering
- `logger.exception()` → `logger.exception()` (structlog handles this natively)

## Event Type Taxonomy for DevPulse

| Namespace | Use for | Examples |
|-----------|---------|----------|
| `system.startup` | App boot, scheduler init | Lifespan start/stop |
| `system.shutdown` | Graceful shutdown | Lifespan cleanup |
| `system.config` | Config validation | Missing JWT secret |
| `system.http` | Request lifecycle | Middleware request.completed |
| `system.sync` | Sync orchestration | Sync start/complete/fail/cancel |
| `system.github_api` | GitHub API interactions | Rate limits, auth errors |
| `system.scheduler` | APScheduler events | Job scheduling, rescheduling |
| `system.webhook` | Webhook processing | Webhook receive/error |
| `system.slack` | Slack integration | DM send, notification failures |
| `system.db` | Database operations | Connection issues (future) |
| `ai.analysis` | AI analysis calls | Claude API requests |
| `ai.categorization` | Work categorization | AI batch classification |
| `ai.settings` | AI settings changes | Budget, toggles |
| `frontend.error` | Frontend error reports | Uncaught errors, API failures |

## Key Decisions
- **No behavior changes**: Every existing log call must produce equivalent output. This is a mechanical migration.
- **Keyword args over format strings**: `logger.info("Found %d PRs", count)` → `logger.info("Found PRs", count=count)` — enables structured querying in Loki
- **`_add_log()` untouched**: The JSONB log_summary is a separate concern (user-facing sync progress UI). It coexists with structlog.
- **`SyncContext.sync_logger` type**: Change from `logging.Logger` to structlog `BoundLogger`. Update the field type and default factory.
