# Task M-07: Remove HTTPException from Service Layer

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
`services/ai_settings.check_feature_enabled()`, `services/ai_settings.check_budget()`, and `services/ai_analysis.run_analysis()` raise `HTTPException` directly from the service layer. This violates the thin-router convention and tightly couples services to FastAPI's HTTP layer, making them:
- Harder to test without the FastAPI test client
- Impossible to call from non-HTTP contexts (scheduled jobs, CLI tools)

### Fix
Replace `HTTPException` raises in services with custom exception classes (e.g., `FeatureDisabledError`, `BudgetExceededError`). Catch these in the API routes and convert to appropriate HTTP responses.

### Files
- `backend/app/services/ai_settings.py` — `check_feature_enabled()`, `check_budget()`
- `backend/app/services/ai_analysis.py` — error handling
- `backend/app/api/ai_analysis.py` — catch service exceptions, convert to HTTPException

### Architecture Docs
- `docs/architecture/API-DESIGN.md` — Architectural Concerns
- `docs/architecture/SERVICE-LAYER.md` — AI Integration section
