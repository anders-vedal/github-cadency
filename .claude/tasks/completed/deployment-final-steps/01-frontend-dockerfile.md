# Task 1: Make Frontend Dockerfile Production-Ready

**Status:** complete
**Blocks:** Task 2 (docker-compose hardening)

## Problem

The current `frontend/Dockerfile` runs `pnpm dev --host` (Vite dev server with hot-reload). This is not suitable for production — it's slow, unoptimized, and exposes Vite internals.

## Current State

**`frontend/Dockerfile`:**
```dockerfile
FROM node:22-slim
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --no-frozen-lockfile
COPY . .
CMD ["sh", "-c", "pnpm install --no-frozen-lockfile && pnpm dev --host"]
```

- No build step — serves uncompiled source via Vite dev server
- `--no-frozen-lockfile` means non-deterministic installs
- No static file serving — Vite dev server handles everything including `/api/*` proxy

**`frontend/package.json` build script:** `"build": "tsc -b && vite build"` — exists but is never called by the Dockerfile.

## Changes Required

### 1. Rewrite `frontend/Dockerfile` as multi-stage build

```dockerfile
# Stage 1: Build
FROM node:22-slim AS build
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 5173
```

**Why multi-stage:**
- Stage 1 installs deps + builds → produces static `dist/` folder
- Stage 2 copies only the built output into a tiny nginx image (~40MB vs ~400MB)
- No node_modules, no source code, no dev tooling in the final image

**Why `--frozen-lockfile`:** Ensures deterministic builds. If `pnpm-lock.yaml` is out of sync with `package.json`, the build fails loudly instead of silently resolving different versions.

### 2. Create `frontend/nginx.conf`

```nginx
server {
    listen 5173;

    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback — all non-file routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy to backend container
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Cache static assets (Vite hashes filenames, so immutable caching is safe)
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

**Why port 5173:** Keeps the same internal port so `docker-compose.yml` port mapping (`3001:5173`) doesn't change.

**Why `/api/` proxy here:** In dev, Vite's built-in proxy handles `/api/*` → `localhost:8000`. In production, nginx takes over this role. The backend is reachable as `http://backend:8000` via Docker's internal DNS.

**Why SPA fallback:** React Router uses client-side routing. Without `try_files`, refreshing on `/admin/team` would 404. The fallback serves `index.html` for all non-file paths, letting React Router handle the route.

### 3. Update `docker-compose.override.yml`

Add `target: build` so dev mode uses only Stage 1 (the node image, not nginx):

```yaml
frontend:
  build:
    context: ./frontend
    target: build
  command: ["sh", "-c", "pnpm install --no-frozen-lockfile && pnpm dev --host"]
  volumes:
    - ./frontend:/app
    - /app/node_modules
```

**Why `target: build`:** In dev, we want the node environment for hot-reload. The `command` override replaces the build CMD with the dev server. Volume mounts enable file watching.

**Why `--no-frozen-lockfile` in dev only:** During development, you often add packages. Strict lockfile would require running `pnpm install` on the host first. The production Dockerfile still uses `--frozen-lockfile`.

## Verification

```bash
# Build production image
docker compose -f docker-compose.yml build frontend

# Check image size (should be ~40-50MB, not ~400MB)
docker images | grep frontend

# Start production stack and verify
docker compose -f docker-compose.yml up -d
curl -s http://localhost:3001          # should return index.html
curl -s http://localhost:3001/api/health  # should proxy to backend

# Verify dev mode still works
docker compose up -d  # uses override
# Frontend at localhost:3001 should have hot-reload
```
