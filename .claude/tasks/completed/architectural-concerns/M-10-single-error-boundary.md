# Task M-10: Add Per-Section Error Boundaries

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
There is a single `ErrorBoundary` in `App.tsx` wrapping all protected routes. If any page component throws during render, the entire app shows the generic "Something went wrong" UI. The user must click "Try Again" or "Go to Dashboard" to recover — they cannot navigate to other working pages.

### Fix
Add error boundaries at the section level:
1. Wrap each `SidebarLayout` (insights, admin) content in its own `ErrorBoundary`
2. Wrap top-level pages (`Dashboard`, `ExecutiveDashboard`, `DeveloperDetail`) individually
3. Keep the global `ErrorBoundary` as a last-resort catch-all

This way a crash in one page only affects that page — sidebar nav and header remain functional.

### Files
- `frontend/src/App.tsx` — add per-section `ErrorBoundary` wrappers
- `frontend/src/components/ErrorBoundary.tsx` — optionally add a `resetOnNavigate` prop

### Architecture Docs
- `docs/architecture/FRONTEND.md` — Error/Loading Patterns section
