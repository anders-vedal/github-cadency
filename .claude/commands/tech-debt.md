Scan the DevPulse project for tech debt, outdated dependencies, and security concerns.

## Arguments
$ARGUMENTS — Optional: specific area to scan (e.g., "dependencies", "security", "code-quality") or "all" (default: all)

## Instructions

Perform a comprehensive tech debt scan of the DevPulse codebase.

### 1. Dependency Health
- Read `backend/requirements.txt` or `backend/pyproject.toml` — list all dependencies with pinned versions
- Read `frontend/package.json` — list all dependencies with pinned versions
- Flag any dependencies that look very old
- Flag missing lockfiles
- Check for unused dependencies

### 2. Security Concerns
- Search for hardcoded secrets, API keys, passwords (patterns: "sk-", "api_key=", "password=", "secret=", tokens in code)
- Check .gitignore — does it exclude .env, __pycache__, node_modules?
- Check for SQL injection risks (raw SQL without parameterized queries)
- Check for missing input validation on API endpoints
- Verify GitHub webhook HMAC validation is in place
- Check that GitHub App tokens are not logged or exposed

### 3. Code Quality
- Search for TODO, FIXME, HACK, XXX comments — list each with file and context
- Find files over 500 lines
- Check for dead code: unused imports, commented-out code
- Check for missing type hints on Python function signatures (sample 10 files)
- Check for print() statements (should use logging)

### 4. Infrastructure Gaps
- Missing Dockerfile
- Missing CI/CD configuration
- Missing linting config (ruff, eslint, biome)
- Missing pre-commit hooks
- Check if .env.example exists

### 5. Test Coverage Gaps
- Find source files with no corresponding test file
- Find API routes with no test coverage
- Check for test fixtures vs inline test data

### Output Format

```
## DevPulse Tech Debt Report

### Dependency Health — [GOOD/WARN/BAD]
| Dependency | Version | Concern |
|-----------|---------|---------|

### Security — [GOOD/WARN/BAD]
| Issue | File | Line | Severity |
|-------|------|------|----------|

### Code Quality — [GOOD/WARN/BAD]
TODOs/FIXMEs: X total
Large files (>500 lines): [list]

### Infrastructure Gaps — [GOOD/WARN/BAD]
| Item | Status |
|------|--------|

### Test Gaps — [GOOD/WARN/BAD]
Untested source files: [list]
Untested routes: [list]

### Top 5 Debt Items (prioritized)
1. [most critical]
2. ...
```

If a focus area was provided as argument, only scan and report on that area.
