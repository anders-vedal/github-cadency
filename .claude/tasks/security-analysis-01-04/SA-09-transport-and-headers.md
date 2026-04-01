# SA-09: Transport Security, Headers, and Production Hardening

**Priority:** Planned
**Severity:** MEDIUM (#15, #18), LOW (#21)
**Effort:** Medium
**Status:** Done

## Findings

### Finding #15: No HTTPS Enforcement
- **File:** `backend/app/main.py:297-302`
- No TLS termination, no HSTS header, no security headers
- JWT Bearer tokens and OAuth tokens travel over HTTP
- `frontend_url` defaults to `http://localhost:3001`

### Finding #18: `--reload` in Production Dockerfile
- **File:** `backend/Dockerfile:10`
- CMD includes `--reload` — enables Uvicorn file watcher in production
- Combined with volume mount, source changes trigger immediate restarts

### Finding #21: OpenAPI/Swagger Docs Exposed Unauthenticated
- **File:** `backend/app/main.py:286-291`
- `/docs` and `/openapi.json` accessible without auth
- Full API schema provides a complete attack surface map

## Required Changes

### 1. Add security headers middleware (`backend/app/main.py`)
- Add a middleware that sets security headers on all responses:
  ```python
  @app.middleware("http")
  async def security_headers(request, call_next):
      response = await call_next(request)
      response.headers["X-Content-Type-Options"] = "nosniff"
      response.headers["X-Frame-Options"] = "DENY"
      response.headers["X-XSS-Protection"] = "0"  # Modern browsers, CSP preferred
      response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
      if settings.environment == "production":
          response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
      return response
  ```

### 2. Add `ENVIRONMENT` config (`backend/app/config.py`)
- Add `environment: str = "development"` to settings
- Use it to conditionally:
  - Enable HSTS (production only)
  - Disable OpenAPI docs (production only)
  - Control `--reload` behavior

### 3. Disable OpenAPI in production (`backend/app/main.py`)
- Conditionally disable docs:
  ```python
  app = FastAPI(
      docs_url="/docs" if settings.environment != "production" else None,
      redoc_url="/redoc" if settings.environment != "production" else None,
      openapi_url="/openapi.json" if settings.environment != "production" else None,
  )
  ```

### 4. Fix Dockerfile (`backend/Dockerfile`)
- Remove `--reload` from the production CMD:
  ```dockerfile
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
- Add `--reload` only in `docker-compose.override.yml` for development:
  ```yaml
  backend:
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```

### 5. Add non-root user to Dockerfile (`backend/Dockerfile`)
- Add a `USER` directive:
  ```dockerfile
  RUN adduser --disabled-password --gecos '' appuser
  USER appuser
  ```

### 6. Document TLS termination
- Add a section to `.env.example` or a deployment guide explaining:
  - Use a reverse proxy (nginx, Caddy, Traefik) for TLS termination
  - Set `FRONTEND_URL` to `https://...` in production
  - Update CORS `allow_origins` to match the production domain

## Impact Analysis

### Will this break anything?

**Security headers middleware — no conflicts.** The LIFO middleware rule means a `@app.middleware("http")` decorator registers outermost, running before CORS. Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) don't conflict with CORS headers. They apply to all responses including preflight `OPTIONS`. No issue.

**X-Frame-Options: DENY — safe.** No `<iframe>` usage found anywhere in `frontend/src`. No component renders the app inside a frame. The header applies to API responses only (the React SPA is served by the Vite/frontend server, not the backend).

**No dangerouslySetInnerHTML.** No uses found in the frontend. CSP headers (if added later) would not break anything.

**Disabling /docs in production — safe.** No test file accesses `/docs` or `/openapi.json`. No healthcheck tooling depends on it. The `/api/health` endpoint at `main.py:320` is separate and unaffected.

**Dockerfile base image — supports non-root.** `python:3.11-slim` is Debian-based; `adduser` is available.

**docker-compose.yml does NOT override CMD.** No `command:` key exists for the backend service — the Dockerfile CMD is the active entrypoint. Removing `--reload` takes effect. However, `docker-compose.yml:29` mounts `./backend:/app` as a volume (useful for dev). The volume mount should move to a `docker-compose.override.yml` for dev only — no override file exists yet, so one must be created.

**`environment` config — doesn't exist yet.** Must add `environment: str = "development"` to Settings. The existing `log_format` field already uses a similar dev/prod pattern, so this fits naturally.

### Exact files to modify

| File | Change | Risk |
|------|--------|------|
| `backend/app/config.py` | Add `environment: str = "development"` | None |
| `backend/app/main.py:~291` | Conditionally disable `/docs` based on `environment` | None |
| `backend/app/main.py:~302` | Add security headers middleware | None |
| `backend/Dockerfile:10` | Remove `--reload` from CMD | None |
| `backend/Dockerfile` | Add `RUN adduser` + `USER appuser` | Low — PEM must be readable |
| `docker-compose.override.yml` (new) | Dev-only: `command: ... --reload`, volume mount | None |
| `.env.example` | Document `ENVIRONMENT` setting | Documentation |

### Edge cases

- The non-root `appuser` must be able to read the PEM file mounted at `/app/github-app.pem:ro`. This depends on host file permissions — the PEM must be world-readable (`chmod 644`) or owned by the container UID.
- The volume mount `./backend:/app` in `docker-compose.yml` should move to the override file for production. For now, it's only used in the dev Docker setup.

## Testing

- Test: security headers present on all API responses (check `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)
- Test: HSTS header present only when `ENVIRONMENT=production`
- Test: `/docs` returns 404 when `ENVIRONMENT=production`
- Test: `/docs` works normally in development (default)
- Test: Docker container runs as non-root user
- Test: app starts without `--reload` in production Dockerfile
