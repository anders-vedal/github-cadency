# TD-02: CI/CD Pipeline & Linting Infrastructure

## Status: TODO
## Priority: HIGH
## Effort: Medium (half day)

## Summary

The project has no CI/CD pipeline, no Python linter/type-checker, no pre-commit hooks, and no formatter. This means broken tests, type errors, and lint violations can merge undetected. This is the single most impactful infrastructure gap.

## Tasks

### 1. Add GitHub Actions CI workflow
**Create:** `.github/workflows/ci.yml`
**Jobs:**
- **backend-test:** Python 3.11+, install deps, run `pytest` (SQLite in-memory — no Postgres needed)
- **backend-lint:** Run ruff check + ruff format --check
- **frontend-build:** pnpm install, `pnpm build` (type-check + bundle)
- **frontend-lint:** `pnpm lint` (eslint)
- **frontend-test:** `pnpm test` (vitest, when tests exist)

**Triggers:** push to `main`, all PRs

### 2. Add Python linter (ruff)
**Create:** `backend/ruff.toml` (or `[tool.ruff]` in a `pyproject.toml`)
**Config:**
- Target: Python 3.11
- Rule sets: `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `UP` (pyupgrade)
- Start with `--fix` on safe rules only
- Line length: 120 (match existing code style)
- Exclude: `migrations/versions/`

### 3. Add pre-commit hooks
**Create:** `.pre-commit-config.yaml`
**Hooks:**
- `ruff` (lint + format) for Python
- `eslint` for frontend (via local hook)
- Trailing whitespace, end-of-file fixer, check-yaml, check-json

### 4. Add Python type checker (optional, lower priority)
**Tool:** mypy or pyright
**Scope:** Start with `--ignore-missing-imports` and gradually tighten
**Note:** The codebase has good type hints on service functions but gaps in API routes and webhooks (see TD-01 acceptance criteria). Run in CI as warning-only initially.

### 5. Add frontend formatter (optional)
**Tool:** Prettier (`.prettierrc`) or Biome (`biome.json`)
**Scope:** Format `.ts`, `.tsx`, `.css`, `.json` files
**Note:** Lower priority — ESLint is already configured

## Acceptance Criteria

- [ ] GitHub Actions runs tests + lint on every PR
- [ ] `ruff check` passes on the backend codebase
- [ ] Pre-commit hooks installed and documented in CLAUDE.md
- [ ] CI blocks merge on test failure or lint error
- [ ] Existing code passes all new checks (fix or suppress as needed)

## Notes

- The backend test suite uses SQLite in-memory via aiosqlite — no PostgreSQL service needed in CI
- Frontend has only 3 test files currently (see TD-03) — the test job will be fast but minimal
- Consider adding a `Makefile` or `justfile` for common dev commands (`make test`, `make lint`, `make fmt`)
