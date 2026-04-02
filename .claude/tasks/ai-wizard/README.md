# AI Analysis Wizard

Multi-step wizard replacing the current dialog-based AI analysis trigger. Adds info cards explaining each analysis type, adaptive scope configuration, time range + repo filter, accurate cost estimation via dry-run, and a configurable auto-schedule system.

## Task Dependency Graph

```
AW-01 Backend: Dry-Run Estimation + Repo Filtering
  ├── AW-02 Backend: Schedule System
  │     └── AW-04 Frontend: Landing Page + Schedule Management
  └── AW-03 Frontend: Wizard
        └── AW-04 Frontend: Landing Page + Schedule Management
```

## Tasks

| ID | Title | Status | Depends On |
|----|-------|--------|------------|
| AW-01 | Backend — Accurate Dry-Run Cost Estimation & Repo Filtering | completed | — |
| AW-02 | Backend — AI Analysis Schedule System | completed | AW-01 |
| AW-03 | Frontend — AI Analysis Wizard | completed | AW-01 |
| AW-04 | Frontend — AI Landing Page Refactor & Schedule Management | completed | AW-02, AW-03 |

## Key Design Decisions

- **Single wizard, choice at the end**: Users configure what to analyze (steps 1-3), then choose "Run Now" or "Save as Schedule" on the confirm step
- **Multiple independent schedules**: Each schedule is a separate DB row with its own type, scope, repo filter, and cron frequency
- **Dry-run estimation**: Confirm step builds the real context (same DB queries as the actual analysis) to measure character count and derive accurate token estimates
- **Pre-filling from URL params**: DeveloperDetail links to `/admin/ai/new?type=one_on_one_prep&developer_id=123`, wizard pre-fills and skips to step 2
- **Repo filtering**: Optional advanced section in step 3, passed through to all data-gathering functions
