---
purpose: "Navigation hub for architecture documentation"
last-updated: "2026-03-29"
related:
  - docs/architecture/OVERVIEW.md
  - docs/architecture/DATA-MODEL.md
  - docs/architecture/API-DESIGN.md
  - docs/architecture/SERVICE-LAYER.md
  - docs/architecture/FRONTEND.md
  - docs/architecture/DATA-FLOWS.md
---

# Architecture Documentation

This directory contains interconnected architecture documents for DevPulse. Generated and maintained by `/architect`.

## Quick Navigation

| I want to understand... | Read this | Key sections |
|------------------------|-----------|--------------|
| How the system fits together | [OVERVIEW.md](OVERVIEW.md) | Architecture diagram, component map |
| How database tables relate | [DATA-MODEL.md](DATA-MODEL.md) | ER diagram, table relationships |
| Why FKs are nullable / JSONB decisions | [DATA-MODEL.md](DATA-MODEL.md) | Design decisions |
| How API routes are organized | [API-DESIGN.md](API-DESIGN.md) | Route organization, auth model |
| What each service does | [SERVICE-LAYER.md](SERVICE-LAYER.md) | Service responsibility map |
| How GitHub sync works end-to-end | [DATA-FLOWS.md](DATA-FLOWS.md) | Sync pipeline flow |
| How the frontend is structured | [FRONTEND.md](FRONTEND.md) | Routing, component hierarchy |
| How stats are computed | [SERVICE-LAYER.md](SERVICE-LAYER.md) | Key algorithms |
| How AI analysis works | [DATA-FLOWS.md](DATA-FLOWS.md) | AI analysis lifecycle |
| How auth works | [DATA-FLOWS.md](DATA-FLOWS.md) | Auth flow |
| How Slack notifications work | [DATA-FLOWS.md](DATA-FLOWS.md) | Slack notification flow |

## Related References

- [CLAUDE.md](../../CLAUDE.md) — Conventions, patterns, and project reference
- [docs/API.md](../API.md) — Complete API endpoint catalog
- [DEVPULSE_SPEC.md](../../DEVPULSE_SPEC.md) — Full technical specification

## Keeping Docs Current

Run `/architect` (full audit) or `/architect <area>` (focused update) after structural changes. The `/document-changes` skill also checks these docs. See the Architecture Advisory table in CLAUDE.md for guidance on when to consult these docs.
