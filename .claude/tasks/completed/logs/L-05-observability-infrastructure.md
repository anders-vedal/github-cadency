# Task L-05: Observability Infrastructure (Loki/Promtail/Grafana/Prometheus)

## Status
completed

## Blocked By
- L-01

## Blocks
- L-06

## Description
Add the full observability stack to Docker Compose: Promtail collects container stdout, ships to Loki for storage, Grafana for visualization, Prometheus + cAdvisor for container metrics. Based on the infrastructure configs at `.claude/docs/logging-export/infrastructure/`.

## Deliverables

- [ ] **infrastructure/promtail-config.yml** — Promtail config:
  - Docker service discovery (auto-discovers containers)
  - Container filter: keep only `.*-(backend|frontend).*` containers
  - Pipeline: parse Docker JSON wrapper → extract structlog JSON fields (`level`, `event_type`, `request_id`, `event`) → promote `level` and `event_type` to Loki labels
  - Adapted from reference: remove `org_id` extraction (no multi-tenancy), keep `request_id` as parsed field (high cardinality)
- [ ] **infrastructure/loki-config.yml** — Loki config:
  - TSDB schema v13, filesystem storage
  - 90-day retention (`retention_period: 2160h`)
  - Compaction every 10m with 2h delete delay
  - Ingestion limits: 10MB/s rate, 20MB/s burst
- [ ] **infrastructure/prometheus.yml** — Prometheus config:
  - Scrape cAdvisor (container metrics) at 15s interval
  - Scrape Loki internal metrics
  - Placeholder for future backend `/metrics` endpoint
- [ ] **infrastructure/grafana/provisioning/datasources/datasources.yml** — Auto-provision Loki + Prometheus as Grafana data sources
- [ ] **infrastructure/grafana/provisioning/dashboards/dashboards.yml** — Dashboard provisioning config
- [ ] **infrastructure/grafana/dashboards/devpulse-app-health.json** — Pre-built dashboard:
  - Error rate panel: `{level="error"} | json`
  - Request latency p95: `{event_type="system.http"} | json | unwrap duration_ms`
  - Log volume by level: `sum by (level) (rate({service=~".*backend.*"}[5m]))`
  - Frontend errors: `{event_type="frontend.error"} | json`
  - Recent errors table: last 50 error-level logs
- [ ] **docker-compose.yml** — Add services:
  - `loki` (grafana/loki:3.4.2) — port 3100, volume for chunks
  - `promtail` (grafana/promtail:3.4.2) — mount Docker socket + promtail config
  - `grafana` (grafana/grafana:11.6.0) — port 3002, provisioning volumes, anonymous auth enabled for dev
  - `prometheus` (prom/prometheus:v3.2.1) — port 9090, config volume
  - `cadvisor` (gcr.io/cadvisor/cadvisor:v0.51.0) — mount /var/run/docker.sock, /sys, /var/lib/docker (read-only)
  - All observability services in a `logging` Docker Compose profile so they can be toggled: `docker compose --profile logging up`
- [ ] **docker-compose.yml** — Add `logging` config to backend service:
  ```yaml
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
  ```

## Key Decisions
- **Docker Compose profile `logging`**: Observability stack is opt-in via `docker compose --profile logging up`. Running plain `docker compose up` still works without the logging stack — no overhead for quick dev sessions.
- **Grafana anonymous auth**: Enabled for local dev (no login needed). Not for production.
- **Grafana on port 3002**: Avoids conflict with frontend (3001) and backend (8000).
- **Pre-built dashboard**: One dashboard with the most useful panels out of the box. Users can create more in Grafana.
- **No alerting rules**: Out of scope. Grafana alerting can be configured manually later.
- **Image versions**: Pin to specific recent versions for reproducibility.

## Reference
- `.claude/docs/logging-export/infrastructure/promtail-config.yml`
- `.claude/docs/logging-export/infrastructure/loki-config.yml`
- `.claude/docs/logging-export/infrastructure/prometheus.yml`
