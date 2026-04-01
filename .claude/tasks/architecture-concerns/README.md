# Architecture Concerns — 2026-04-01

Architectural concerns discovered during `/architect` full audit on 2026-04-01. Organized by subsystem into 4 tasks.

## Task Overview

| Task | Subsystem | Severity | Findings | Effort |
|------|-----------|----------|----------|--------|
| [AC-01](AC-01-notification-backend.md) | Notification backend | Medium | 6 issues — missing toggles, dead return, memory pagination, scheduler, evaluator dispatch, webhook gap | Medium |
| [AC-02](AC-02-notification-frontend.md) | Notification frontend | Medium | 4 issues — no polling, label duplication, non-clickable link, ErrorCard prop | Low |
| [AC-03](AC-03-sync-and-webhooks.md) | Sync & webhooks | Medium | 6 issues — APScheduler blocking, auto-reactivation, webhook all-or-nothing, approval staleness, URL parsing, no dedup | Medium |
| [AC-04](AC-04-api-and-data-model.md) | API & data model | Low-Medium | 6 issues — inline business logic, circular import, CLAUDE.md table count, service-only FK enforcement, silent no-ops | Low |

## Severity Distribution

- **Medium:** 12 findings (AC-01, AC-02, AC-03)
- **Low:** 10 findings (AC-03, AC-04)
