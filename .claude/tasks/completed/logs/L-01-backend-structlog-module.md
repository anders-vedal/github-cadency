# Task L-01: Backend Structlog Module

## Status
completed

## Blocked By
None

## Blocks
- L-02, L-03, L-04, L-05, L-06

## Description
Create the core structured logging module under `backend/app/logging/` that replaces Python's built-in `logging` with structlog. This is the foundation for all other logging tasks.

Based on the reference implementation at `.claude/docs/logging-export/source/logging.py`.

## Deliverables

- [x] **backend/app/logging/__init__.py** — Public API: `configure_logging`, `get_logger`
- [x] **backend/app/logging/config.py** — `configure_logging(json_output: bool = True, level: str = "INFO")` function that sets up structlog with the processor pipeline:
  1. `merge_contextvars` — auto-inject request-scoped context (request_id, method, path)
  2. `add_log_level` — adds `level` field
  3. `StackInfoRenderer` — renders stack traces
  4. `TimeStamper(fmt="iso")` — ISO 8601 timestamps
  5. `JSONRenderer` (prod) or `ConsoleRenderer` (dev) — based on `json_output` param
  - Uses `make_filtering_bound_logger()` for level filtering
  - Uses `PrintLoggerFactory()` for stdout-only output
- [x] **backend/app/logging/config.py** — `get_logger(name: str | None = None)` wrapper around `structlog.get_logger()`
- [x] **backend/requirements.txt** — Add `structlog>=24.1`
- [x] **backend/app/main.py** — Call `configure_logging()` at module level (before any logger creation), using `LOG_FORMAT` and `LOG_LEVEL` env vars
- [x] **backend/app/config.py** — Add `log_format: str = "console"` and `log_level: str = "INFO"` to Settings
- [x] **backend/tests/unit/test_logging.py** — Basic tests: `configure_logging` callable, `get_logger` returns bound logger, JSON output mode produces valid JSON

## Key Decisions
- **stdout-only**: No file handlers, no syslog. Containers collect stdout natively.
- **Two env vars**: `LOG_FORMAT` (`json` for prod, anything else for dev console) and `LOG_LEVEL` (`DEBUG`/`INFO`/`WARNING`/`ERROR`)
- **Module path**: `backend/app/logging/` (not a separate package per user preference)
- **No audit events**: Skipped per user decision — DevPulse doesn't need SOC 2 compliance

## Reference
- `.claude/docs/logging-export/source/logging.py` — configure_logging + get_logger
- `.claude/docs/logging-export/source/__init__.py` — public API pattern
