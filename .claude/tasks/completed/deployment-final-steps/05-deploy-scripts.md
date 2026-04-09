# Task 5: Add Deploy Helper Scripts

**Status:** done
**Blocks:** Task 6 (GitHub Actions CI/CD — calls `deploy.sh`)

## Problem

No automation for backup, deploy, or rollback. These operations are manual and error-prone. The CI/CD workflow (Task 6) needs a `deploy.sh` to call.

## Files to Create

### 5a. `scripts/backup-db.sh`

```bash
#!/usr/bin/env bash
# Backs up the DevPulse PostgreSQL database.
# Usage: ./scripts/backup-db.sh [backup_dir]
#   backup_dir defaults to /backups

set -euo pipefail

BACKUP_DIR="${1:-/backups}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/devpulse-${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up database to ${BACKUP_FILE}..."
docker exec devpulse-db-1 pg_dump -U devpulse devpulse | gzip > "$BACKUP_FILE"
echo "Backup complete: ${BACKUP_FILE} ($(du -h "$BACKUP_FILE" | cut -f1))"

# Retention: delete backups older than 30 days
find "$BACKUP_DIR" -name "devpulse-*.sql.gz" -mtime +30 -delete
echo "Cleaned up backups older than 30 days."
```

**Notes:**
- `set -euo pipefail`: exit on any error, undefined variable, or pipe failure
- Container name `devpulse-db-1` follows Docker Compose v2 naming convention (project_service_index). The project name defaults to the directory name (`devpulse` if cloned to `/opt/devpulse`).
- Retention cleanup runs every time. `find -mtime +30` means files older than 30 days.
- Backup size for a typical team (~50 devs, ~100 repos, 6 months data): ~5-20MB compressed.

### 5b. `scripts/deploy.sh`

```bash
#!/usr/bin/env bash
# Deploy DevPulse. Called by GitHub Actions CI/CD or manually.
# Usage: ./scripts/deploy.sh
#
# Expects:
#   - Working directory is the repo root (/opt/devpulse)
#   - .env file exists (or is symlinked from /etc/devpulse/.env)
#   - Docker Compose v2 is installed

set -euo pipefail

COMPOSE="docker compose -f docker-compose.yml"
BACKUP_DIR="/backups"

echo "=== DevPulse Deploy ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Commit: $(git rev-parse --short HEAD)"

# 1. Pre-deploy backup (skip if DB container isn't running — first deploy)
echo "--- Pre-deploy backup ---"
if docker ps --format '{{.Names}}' | grep -q devpulse-db-1; then
    ./scripts/backup-db.sh "$BACKUP_DIR"
else
    echo "Database container not running, skipping backup (first deploy?)"
fi

# 2. Build new images
echo "--- Building images ---"
$COMPOSE build

# 3. Restart services (recreates only changed containers)
echo "--- Starting services ---"
$COMPOSE up -d

# 4. Wait for backend health check
echo "--- Waiting for backend health check ---"
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "Backend is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Backend health check failed after 60 seconds"
        echo "--- Last 20 backend log lines ---"
        $COMPOSE logs backend --tail 20
        exit 1
    fi
    sleep 2
done

echo "=== Deploy complete ==="
```

**Notes:**
- No `git pull` — the CI/CD workflow handles that before calling this script. For manual deploys, run `git pull origin main` first.
- Health check: 30 attempts x 2 second sleep = 60 second timeout. The backend needs time for Alembic migrations + APScheduler startup.
- On failure: prints last 20 log lines and exits non-zero. GitHub Actions will show the failure.
- `$COMPOSE up -d` only recreates containers whose images changed. Unchanged services (e.g., `db`) are not restarted.

### 5c. `scripts/rollback.sh`

```bash
#!/usr/bin/env bash
# Rollback to the previous git commit and redeploy.
# Optionally restore a database backup.
#
# Usage:
#   ./scripts/rollback.sh                          # rollback code only
#   ./scripts/rollback.sh --restore-db BACKUP_FILE  # also restore a DB backup
#
# To find available backups: ls -lth /backups/

set -euo pipefail

COMPOSE="docker compose -f docker-compose.yml"
RESTORE_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --restore-db)
            RESTORE_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--restore-db BACKUP_FILE]"
            exit 1
            ;;
    esac
done

echo "=== DevPulse Rollback ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 1. Revert to previous commit
CURRENT=$(git rev-parse --short HEAD)
echo "Current commit: $CURRENT"
git checkout HEAD~1
echo "Rolled back to: $(git rev-parse --short HEAD)"

# 2. Restore DB backup if requested
if [ -n "$RESTORE_FILE" ]; then
    echo "--- Restoring database from $RESTORE_FILE ---"
    if [ ! -f "$RESTORE_FILE" ]; then
        echo "ERROR: Backup file not found: $RESTORE_FILE"
        exit 1
    fi
    gunzip < "$RESTORE_FILE" | docker exec -i devpulse-db-1 psql -U devpulse devpulse
    echo "Database restored."
fi

# 3. Rebuild and restart
echo "--- Rebuilding and restarting ---"
$COMPOSE build
$COMPOSE up -d

echo ""
echo "=== Rollback complete ==="
echo "You are now on a detached HEAD. To make this permanent:"
echo "  git revert $CURRENT && git push origin main"
echo ""
echo "This will trigger a clean CI/CD deploy of the reverted state."
```

**Notes:**
- `git checkout HEAD~1` puts you in detached HEAD state. This is intentional — it's a quick fix, not a permanent state.
- The script tells you the next step: `git revert` the bad commit and push. This triggers a proper CI/CD deploy.
- DB restore is optional because most deploys only change code, not schema. If a bad migration ran, you need `--restore-db`.

### 5d. File permissions

```bash
chmod +x scripts/backup-db.sh scripts/deploy.sh scripts/rollback.sh
```

Or via git (preserves executable bit across clones):
```bash
git update-index --chmod=+x scripts/backup-db.sh scripts/deploy.sh scripts/rollback.sh
```

## Verification

```bash
# Test backup (requires running DB container)
./scripts/backup-db.sh /tmp/test-backups
ls -lh /tmp/test-backups/  # should show a .sql.gz file

# Test deploy (locally)
./scripts/deploy.sh
# Should build, start, and pass health check

# Test rollback (on a test branch, not main)
git checkout -b test-rollback
git commit --allow-empty -m "test commit"
./scripts/rollback.sh
git checkout main
git branch -D test-rollback
```
