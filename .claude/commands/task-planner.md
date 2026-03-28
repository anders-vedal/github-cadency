---
description: Guided feature development with codebase understanding and architecture focus
argument-hint: Optional feature description
model: opus
---

# Feature Development

You are helping a developer implement a new feature for DevPulse — an engineering intelligence dashboard. Follow a systematic approach: understand the codebase deeply, clarify requirements, design the architecture, then implement.

## Core Principles

- **CLAUDE.md and DEVPULSE_SPEC.md as source of truth**: Patterns and conventions are documented there. Reference those — don't hardcode details here.
- **Ask clarifying questions**: Identify all ambiguities before designing. Wait for answers before proceeding.
- **Understand before acting**: Read existing code patterns first.
- **Read files identified by agents**: When agents return key file lists, read those files to build context.
- **Use TodoWrite**: Track progress throughout all phases.

---

## Phase 1: Discovery

**Goal**: Understand what needs to be built and determine scope

Initial request: $ARGUMENTS

**Actions**:
1. Create todo list with all phases
2. If feature is unclear, ask user for: What problem are they solving? What should the feature do? Any constraints?
3. **Determine scope type**:
   - **Backend-only**: DB, API, service changes — no UI
   - **Frontend-only**: New/modified pages, components, styling — no new API or DB changes
   - **Full-stack**: Both backend and frontend changes required
4. Present to user: scope type, affected areas, and confirm before proceeding

---

## Phase 2: Codebase Exploration

**Goal**: Understand relevant existing code and patterns

### Backend agents (backend-only or full-stack scope):
Launch code-explorer agents:
- "Find features similar to [feature] and trace their implementation in `backend/app/api/` and `backend/app/services/`"
- "Map the database schema, migrations, and API routes relevant to [feature] in `backend/`"

### Frontend agents (frontend-only or full-stack scope):
Launch code-explorer agents:
- "Analyze existing components and pages relevant to [feature] in `frontend/src/pages/` and `frontend/src/components/` — identify reusable components, layout patterns, and state management approach"
- "Check installed packages in `frontend/package.json`, existing hooks in `frontend/src/hooks/`, and utilities in `frontend/src/utils/`"

### Then:
1. Read all key files identified by agents
2. Present summary of findings and patterns discovered

---

## Phase 3: Clarifying Questions

**Goal**: Resolve all ambiguities before designing

**CRITICAL**: Do not skip this phase.

**Actions**:
1. Review codebase findings and original request
2. Identify underspecified aspects based on scope:
   - **Backend scope**: data model edges, API contract, error handling, migration strategy, GitHub rate limit impact
   - **Frontend scope**: interaction states (loading/empty/error), responsive behavior, dark mode, keyboard navigation
   - **Full-stack**: all of the above plus API-to-UI data flow
3. Present all questions with **why this matters** and **suggestions with pros/cons**
4. Wait for answers before proceeding

---

## Phase 4: Architecture Design

**Goal**: Design the implementation approach

**Actions**:
1. Launch code-architect agents focused on the relevant scope
2. Review approaches and form your recommendation
3. Present to user: summary of approach, trade-offs, your recommendation
4. Ask user which approach they prefer

---

## Phase 5: Technical Specification

**Goal**: Define concrete technical requirements before implementation

### Backend spec (backend-only or full-stack):
- **Database changes**: New tables/columns, Alembic migrations
- **Models**: New SQLAlchemy models and Pydantic schemas
- **API endpoints**: New routes with request/response contracts
- **Services**: Business logic changes

### Frontend spec (frontend-only or full-stack):
- **Component tree**: New/modified components with hierarchy and props
- **State management**: Where state lives, data fetching hooks
- **Interaction spec**: Loading/empty/error states, keyboard navigation
- **Responsive behavior**: Breakpoint handling

### Test strategy:
- Happy-path tests for each new endpoint
- Edge cases (missing data, rate limits, external contributors)

### Then:
1. Present specification including test plan to user for approval

---

## Phase 6: Implementation

**Goal**: Build the feature

**DO NOT START WITHOUT USER APPROVAL on Phase 5**

**Actions**:
1. Read all relevant files identified in previous phases
2. Implement following chosen architecture and project conventions:
   - All I/O async (SQLAlchemy async sessions, httpx.AsyncClient)
   - Type hints + Pydantic models for data contracts
   - Alembic migrations for schema changes
   - GitHub is read-only — never write back
   - AI features off by default
3. Write tests alongside implementation — do not leave tests until the end
4. Update todos as you progress

---

## Phase 6b: Test Verification

**Goal**: Ensure all tests pass

**Actions**:
1. Run linting
2. Run backend tests: `cd backend && python -m pytest`
3. Run frontend tests: `cd frontend && npm test`
4. Fix any failures, re-run until all pass
5. Report summary

---

## Phase 7: Quality Review

**Goal**: Ensure correctness and adherence to conventions

**Actions**:
1. Launch code-reviewer agents in parallel:
   - Simplicity, DRY, and project pattern adherence
   - Bugs, functional correctness, and security
   - Architecture correctness and async patterns
2. Consolidate findings, identify high-severity issues
3. Present findings to user — ask what to fix now vs later
4. Address issues based on user decision

---

## Phase 8: Summary & Documentation

**Goal**: Document what was built

**Actions**:
1. Mark all todos complete
2. Summarize: what was built, key decisions, files modified, schema changes, new endpoints, test count
3. Update `CLAUDE.md` if new key paths, conventions, or API routes were added
