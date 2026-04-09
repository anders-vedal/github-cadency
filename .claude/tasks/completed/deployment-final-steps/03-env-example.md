# Task 3: Update .env.example with Production Guidance

**Status:** done

## Problem

`.env.example` exists and is decent, but:
1. Missing `POSTGRES_PASSWORD` variable (introduced in Task 2)
2. No clear "production checklist" telling you which values MUST be changed
3. Easy to deploy with defaults and not realize you're running with `devpulse:devpulse` credentials

## Changes Required

### 3a. Add production checklist header

Add at the very top of the file:
```bash
# ============================================================
# PRODUCTION CHECKLIST — change ALL of these before deploying:
#
#   1. POSTGRES_PASSWORD  (default: devpulse)
#   2. JWT_SECRET         (generate: openssl rand -hex 32)
#   3. ENCRYPTION_KEY     (generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
#   4. GITHUB_WEBHOOK_SECRET (generate: openssl rand -hex 32)
#   5. GITHUB_APP_ID / INSTALLATION_ID / PRIVATE_KEY_PATH
#   6. GITHUB_CLIENT_ID / CLIENT_SECRET
#   7. GITHUB_ORG
#   8. DEVPULSE_INITIAL_ADMIN
#   9. FRONTEND_URL       (https://your-domain)
#  10. ENVIRONMENT=production
#  11. LOG_FORMAT=json
#  12. GF_ADMIN_PASSWORD  (if using observability stack)
# ============================================================
```

### 3b. Add `POSTGRES_PASSWORD` variable

Add near the top, next to `DATABASE_URL`:
```bash
# PostgreSQL password — used by both the db container and backend DATABASE_URL.
# The docker-compose.yml references this via ${POSTGRES_PASSWORD:-devpulse}.
# CHANGE THIS for any non-local deployment.
# Generate with: openssl rand -hex 16
POSTGRES_PASSWORD=devpulse
```

### 3c. No other changes needed

The rest of the file is already well-documented:
- Secret generation commands are inline
- `ENVIRONMENT` distinguishes dev/prod
- Rate limiting, AI, sync, and DORA configs are clear
- Grafana credentials are documented

## Verification

```bash
# Check that POSTGRES_PASSWORD is in the file
grep POSTGRES_PASSWORD .env.example

# Check the checklist header is present
head -15 .env.example
```
