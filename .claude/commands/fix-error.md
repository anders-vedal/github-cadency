---
description: Systematic error diagnosis and fix — paste an error, get a root-cause analysis and verified fix
argument-hint: Paste error message, stack trace, or describe the problem
model: opus
---

# Error Diagnosis & Fix

You are helping a developer diagnose and fix an error in DevPulse — an engineering intelligence dashboard built with FastAPI + React. Follow a systematic approach: understand the error, investigate root cause, form hypotheses, fix, and verify.

## Core Principles

- **Hypothesis-driven**: Don't explore aimlessly. Form ranked hypotheses and investigate the most likely cause first.
- **Minimal fix**: Fix the root cause with the smallest correct change. Don't refactor surrounding code, add features, or "improve" things while fixing.
- **Verify the fix**: Always run tests and/or reproduce the original error to confirm the fix works.
- **Exit early when appropriate**: Not every error is a code bug. If the root cause is data, config, environment, or tooling — say so, recommend the fix, and stop. Don't force a code change.
- **Use TodoWrite**: Track progress through all phases.

---

## Phase 1: Error Intake & Triage

**Goal**: Parse the error, classify it, and decide which investigation path to follow

**Input**: $ARGUMENTS

**Actions**:
1. Create todo list with all phases
2. **Parse the error** — extract from the input:
   - Error type/class (e.g., `sqlalchemy.exc.IntegrityError`, `TypeError`, HTTP 500, React render error, "empty data", "wrong result")
   - Stack trace file paths and line numbers (if present)
   - Error message text
   - Context: which component, which endpoint/page, which operation
3. **Classify the error category**:
   - **Crash/exception**: Code throws an error — has a stack trace or error message
   - **Wrong result**: Code runs but produces incorrect output — no error, just wrong data
   - **Silent failure**: Feature appears broken but no error — empty data, missing UI, no response
   - **Build/tooling**: Compilation, dependency, migration, or infrastructure failure
4. **Classify severity** (determines which phases to follow):
   - **Quick fix**: Typo, missing import, wrong variable name, obvious off-by-one — skip to Phase 5
   - **Standard**: Known error pattern, clear stack trace, single module — follow all phases
   - **Deep investigation**: No stack trace, intermittent, multi-module, race condition, silent failure — follow all phases with extra exploration
5. **Identify affected scope**:
   - Which layer: database / backend API / frontend / GitHub sync / AI analysis / infrastructure
   - Which module: specific route, service, component, or model
6. Present classification to user and proceed (no approval gate needed for diagnosis)

---

## Phase 2: Reproduction

**Goal**: Confirm the error is real and establish a baseline

### 2a. Live reproduction (when a running instance or test runner is available)

1. Based on error type, attempt reproduction:
   - **Test failure**: Run the specific failing test: `cd backend && python -m pytest <test_file>::<test_name> -xvs`
   - **Backend error**: Check if there's an existing test that covers the failing path. If so, run it.
   - **Frontend error**: Check for related component tests
   - **Build error**: Run the relevant build command (`pip install`, `npm install`, `npm run build`)
   - **Migration error**: Check migration file syntax and ordering
2. Capture the exact reproduction output — this is your "before" baseline
3. If reproduction fails (error doesn't occur), inform user — the error may be environment-specific or intermittent. Ask for more context.

### 2b. Static analysis reproduction (when no running instance is available)

1. **Trace the data flow statically** — read the code path from entry point to output:
   - For API issues: route handler → service → SQLAlchemy query → response construction
   - For UI issues: component mount → data fetch → state update → render
   - For sync issues: GitHub API call → data normalization → upsert → cycle time computation
2. **Check existing test coverage** — are there tests for this path? Do they pass? What do they assert?
3. If static analysis is inconclusive, ask the user to provide browser console / network tab / server log output.

---

## Phase 3: Root Cause Investigation

**Goal**: Trace the error to its origin and form hypotheses

**Actions**:

### 3a. Direct trace (when stack trace is available)
1. Read every file referenced in the stack trace, focusing on the lines mentioned
2. Trace the data flow backward from the error point
3. Check recent changes to these files: `git log --oneline -10 -- <file>` for each file in the trace

### 3b. Contextual investigation (when stack trace is limited or absent)
Launch code-explorer agents in parallel — choose the relevant subset:
- **Backend**: "Find all code paths that could produce the error/empty result for `<endpoint>` in `backend/app/` — trace from route handler through service to database"
- **Frontend**: "Trace the component tree and data flow for `<page>` in `frontend/src/` — identify every fetch call, state update, conditional render, and empty-state guard"
- **GitHub sync**: "Trace the sync flow in `backend/app/services/` for the failing operation — check rate limit handling, data normalization, upsert logic"
- **Database**: "Read the relevant migration files and current models for `<table>` in `backend/`"

### 3c. Pattern matching
Check if this is a known error pattern:
- **SQLAlchemy async session**: Missing `await`, session not properly closed, detached instance
- **GitHub rate limits**: `X-RateLimit-Remaining` not checked, 403 response not handled
- **Nullable FKs**: External contributor with no `developer_id` — null reference
- **JSONB columns**: Incorrect serialization/deserialization of skills, labels, errors
- **Webhook validation**: HMAC mismatch on `X-Hub-Signature-256`
- **Cycle time computation**: Missing timestamps, negative durations, timezone issues
- **Import errors**: Wrong package path, circular imports
- **Frontend**: Missing provider/context wrapper, stale cache, wrong API path

### 3d. Form hypotheses
1. List 1-3 most likely root causes, ranked by probability
2. For each hypothesis, state:
   - **What**: The specific cause
   - **Where**: File and line
   - **Why**: What evidence supports this
   - **Fix preview**: What the fix would look like
3. **Routing decision**:
   - If top hypothesis is a **code bug** → continue to Phase 4
   - If top hypothesis is a **data/config/environment issue** → skip to Phase 4b

---

## Phase 4: Fix Specification (code bugs)

**Goal**: Define the exact code change needed

**SKIP for quick-fix severity** — go straight to Phase 5.

**Actions**:
1. Define the fix: which files change and how
2. **Risk assessment**: Could this fix break other callers? Does it change API contracts or database schema?
3. Present fix plan to user if the fix changes database schema or modifies more than 3 files

---

## Phase 4b: Fix Specification (non-code issues)

**Goal**: Diagnose and recommend fixes for data, config, environment, or tooling problems

**Actions**:
1. **Identify the root artifact** — which config, migration, or data source is wrong
2. **Present recommendation** to user
3. If user agrees to a fix → proceed to Phase 5. If it's a pure environment issue → skip to Phase 8.

---

## Phase 5: Implementation

**Goal**: Apply the minimal correct fix

**Actions**:
1. Read all files that will be modified
2. Apply the fix — follow project conventions:
   - SQLAlchemy 2.0 async sessions
   - Async I/O everywhere (httpx for HTTP)
   - Type hints + Pydantic models
3. If a new test is needed, add it immediately after the fix
4. Update todos

---

## Phase 6: Verification

**Goal**: Confirm the fix works

**Actions**:
1. Reproduce the original error — confirm it now passes
2. Run the test suite for the affected area:
   - Backend: `cd backend && python -m pytest`
   - Frontend: `cd frontend && npm test`
3. If any test fails, adjust the fix and re-verify
4. Report: original error status, test results, any pre-existing issues

---

## Phase 7: Regression Check

**SKIP for**: quick-fix severity where tests pass, or non-code fixes.

**Actions**:
1. Launch a code-reviewer agent to review the diff
2. Check if the same bug pattern exists elsewhere
3. If found, ask user whether to fix those too

---

## Phase 8: Summary

**Actions**:
1. Mark all todos complete
2. Summarize: Error, Root cause, Fix, Tests, Related patterns found
