# Logging & Observability Tasks

Unified structured logging system for DevPulse, based on the Claros observability pattern (`.claude/docs/logging-export/`).

## Goal
Replace ad-hoc `logging.getLogger()` calls with a structlog-based pipeline that outputs JSON to stdout, adds request correlation via middleware, and ships logs to Grafana/Loki for visualization. Frontend errors are also captured and routed through the same pipeline.

## Task Order

| Task | Description | Blocked By |
|------|-------------|------------|
| L-01 | Backend structlog module | — |
| L-02 | Request logging middleware | L-01 |
| L-03 | Migrate all backend loggers | L-01, L-02 |
| L-04 | Frontend error logging + backend ingestion | L-01 |
| L-05 | Observability infrastructure (Loki/Promtail/Grafana) | L-01 |
| L-06 | Environment config, Dockerfiles, event taxonomy | L-01 through L-05 |
