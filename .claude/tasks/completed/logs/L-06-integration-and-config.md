# Task L-06: Environment Config, Dockerfiles & Final Integration

## Status
completed

## Blocked By
- L-01, L-02, L-03, L-04, L-05

## Blocks
None

## Description
Final integration task: wire up environment variables, update Dockerfiles, update `.env.example`, verify the full pipeline end-to-end, and update project documentation.

## Deliverables

- [ ] **.env.example** — Add:
  ```
  LOG_FORMAT=console          # "json" for production, "console" for dev (pretty-print)
  LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
  ```
- [ ] **backend/Dockerfile** — Ensure `structlog` is installed (already in requirements.txt from L-01)
- [ ] **backend/app/config.py** — Verify `log_format` and `log_level` fields are in Settings and wired to `configure_logging()` call in `main.py`
- [ ] **backend/app/main.py** — Verify startup sequence:
  1. `configure_logging()` called first (before any logger creation)
  2. `LoggingContextMiddleware` registered after CORS
  3. Logs router registered
  4. Startup log: `logger.info("DevPulse starting", event_type="system.startup", version=...)`
- [ ] **CLAUDE.md** — Add logging section documenting:
  - `backend/app/logging/` module overview
  - Event type taxonomy table
  - How to add logs in new code (`from app.logging import get_logger`)
  - Infrastructure stack overview (Grafana at :3002, `--profile logging`)
  - Frontend logger usage
- [ ] **End-to-end verification**:
  - `docker compose --profile logging up` boots all services
  - Backend logs appear in Grafana via Loki
  - Frontend error simulation appears in Grafana
  - Request correlation: same `request_id` across middleware + service logs
  - JSON format in Docker, console format in local dev
