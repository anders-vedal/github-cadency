#!/usr/bin/env bash
# =============================================================
# DevPulse .env Generator
# Generates all secrets and prompts for GitHub App values.
# Writes a production-ready .env to /etc/devpulse/.env
#
# Usage:
#   ./scripts/generate-env.sh                # default output to /etc/devpulse/.env
#   ./scripts/generate-env.sh ./test.env     # custom output path
#
# Requirements:
#   - openssl (for secret generation)
#   - python3 + cryptography (for Fernet key — installed by backend requirements.txt)
#     If python3/cryptography is not available, the script will generate a placeholder.
# =============================================================

set -euo pipefail

OUTPUT_FILE="${1:-/etc/devpulse/.env}"
SYMLINK_TARGET="/opt/devpulse/.env"

echo "============================================="
echo "  DevPulse .env Generator"
echo "============================================="
echo ""

# --- Check prerequisites ---
if ! command -v openssl &> /dev/null; then
    echo "ERROR: openssl is required but not found."
    echo "Install with: apt install -y openssl"
    exit 1
fi

# --- Generate secrets ---
echo "Generating secrets..."
POSTGRES_PASSWORD=$(openssl rand -hex 16)
JWT_SECRET=$(openssl rand -hex 32)
WEBHOOK_SECRET=$(openssl rand -hex 32)

# Try to generate Fernet key; fall back to placeholder
ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null) \
    || {
    echo ""
    echo "WARNING: python3 or cryptography package not available."
    echo "  A placeholder ENCRYPTION_KEY will be written."
    echo "  Generate it later with:"
    echo "    python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    echo ""
    ENCRYPTION_KEY="GENERATE_ME_WITH_FERNET"
}

echo "  POSTGRES_PASSWORD:    generated"
echo "  JWT_SECRET:           generated"
echo "  GITHUB_WEBHOOK_SECRET: generated (save this — you'll need it for the GitHub App)"
echo "  ENCRYPTION_KEY:       $([ "$ENCRYPTION_KEY" = "GENERATE_ME_WITH_FERNET" ] && echo "placeholder" || echo "generated")"
echo ""

# --- Prompt for GitHub App values ---
echo "---------------------------------------------"
echo "Enter your GitHub App values."
echo "See docs/DEPLOYMENT.md Section 3 for where to find these."
echo "Press Enter to skip any value (you can edit the .env later)."
echo "---------------------------------------------"
echo ""

read -r -p "GitHub App ID (from app settings page): " GITHUB_APP_ID
GITHUB_APP_ID="${GITHUB_APP_ID:-12345}"

read -r -p "GitHub App Installation ID (from installation URL): " GITHUB_APP_INSTALLATION_ID
GITHUB_APP_INSTALLATION_ID="${GITHUB_APP_INSTALLATION_ID:-67890}"

read -r -p "GitHub OAuth Client ID (from app OAuth settings): " GITHUB_CLIENT_ID
GITHUB_CLIENT_ID="${GITHUB_CLIENT_ID:-Iv1.xxxxxxxxxxxx}"

read -r -s -p "GitHub OAuth Client Secret: " GITHUB_CLIENT_SECRET
echo ""
GITHUB_CLIENT_SECRET="${GITHUB_CLIENT_SECRET:-xxxxxxxxxxxxxxxxxxxx}"

read -r -p "GitHub organization name: " GITHUB_ORG
GITHUB_ORG="${GITHUB_ORG:-your-org-name}"

read -r -p "Your GitHub username (initial admin): " DEVPULSE_INITIAL_ADMIN
DEVPULSE_INITIAL_ADMIN="${DEVPULSE_INITIAL_ADMIN:-your-github-username}"

read -r -p "Production URL (e.g., https://devpulse.yourdomain.com): " FRONTEND_URL
FRONTEND_URL="${FRONTEND_URL:-https://devpulse.yourdomain.com}"

echo ""
read -r -s -p "Anthropic API key (optional, for AI features — press Enter to skip): " ANTHROPIC_API_KEY
echo ""
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"

# --- Write .env file ---
echo ""
echo "Writing $OUTPUT_FILE ..."

# Create file with restrictive permissions before writing secrets
(umask 077 && cat > "$OUTPUT_FILE" << EOF
# =============================================================
# DevPulse Production Configuration
# Generated on $(date -u +%Y-%m-%dT%H:%M:%SZ)
#
# IMPORTANT: This file contains secrets. Keep it secure.
#   chmod 600 $OUTPUT_FILE
# =============================================================

# Database
# Do NOT set DATABASE_URL — docker-compose.yml overrides it automatically.
POSTGRES_PASSWORD=$POSTGRES_PASSWORD

# GitHub App
GITHUB_APP_ID=$GITHUB_APP_ID
GITHUB_APP_PEM_HOST_PATH=/etc/devpulse/github-app.pem
GITHUB_APP_INSTALLATION_ID=$GITHUB_APP_INSTALLATION_ID
GITHUB_WEBHOOK_SECRET=$WEBHOOK_SECRET
GITHUB_ORG=$GITHUB_ORG

# GitHub OAuth
GITHUB_CLIENT_ID=$GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET=$GITHUB_CLIENT_SECRET

# Auth
JWT_SECRET=$JWT_SECRET
DEVPULSE_INITIAL_ADMIN=$DEVPULSE_INITIAL_ADMIN
FRONTEND_URL=$FRONTEND_URL

# Encryption (required for Slack bot token storage)
ENCRYPTION_KEY=$ENCRYPTION_KEY

# Environment
ENVIRONMENT=production
LOG_FORMAT=json
LOG_LEVEL=INFO

# Rate limiting
RATE_LIMIT_ENABLED=true

# Sync schedule
SYNC_INTERVAL_MINUTES=15
FULL_SYNC_CRON_HOUR=2

# DORA Metrics (optional)
DEPLOY_WORKFLOW_NAME=
DEPLOY_ENVIRONMENT=production
HOTFIX_LABELS=hotfix,urgent,incident
HOTFIX_BRANCH_PREFIXES=hotfix/

# AI (optional)
$([ -n "$ANTHROPIC_API_KEY" ] && echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" || echo "# ANTHROPIC_API_KEY=sk-ant-...")

# Grafana (optional — only used with: docker compose --profile logging up)
# GF_ADMIN_USER=admin
# GF_ADMIN_PASSWORD=change-this-password
EOF
)
echo "File written with permissions 600 (owner read/write only)."

# --- Create symlink if needed ---
if [ "$OUTPUT_FILE" = "/etc/devpulse/.env" ] && [ ! -L "$SYMLINK_TARGET" ]; then
    if [ -f "$SYMLINK_TARGET" ]; then
        echo ""
        echo "WARNING: /opt/devpulse/.env already exists as a regular file."
        echo "  Back it up or remove it, then run:"
        echo "  ln -s /etc/devpulse/.env /opt/devpulse/.env"
    elif [ -d "$(dirname "$SYMLINK_TARGET")" ]; then
        ln -s "$OUTPUT_FILE" "$SYMLINK_TARGET"
        echo "Created symlink: $SYMLINK_TARGET -> $OUTPUT_FILE"
    else
        echo "WARNING: $(dirname "$SYMLINK_TARGET") does not exist. Symlink not created."
        echo "  Clone the repo first, then create the symlink manually:"
        echo "  ln -s $OUTPUT_FILE $SYMLINK_TARGET"
    fi
fi

# --- Summary ---
echo ""
echo "============================================="
echo "  .env generated successfully!"
echo "============================================="
echo ""
echo "Secrets generated (save the webhook secret for your GitHub App):"
echo "  GITHUB_WEBHOOK_SECRET=$WEBHOOK_SECRET"
echo ""
DEFAULTS_FOUND=false
DEFAULT_LIST=""
[ "$GITHUB_APP_ID" = "12345" ] && DEFAULTS_FOUND=true && DEFAULT_LIST="${DEFAULT_LIST}\n  - GITHUB_APP_ID"
[ "$GITHUB_APP_INSTALLATION_ID" = "67890" ] && DEFAULTS_FOUND=true && DEFAULT_LIST="${DEFAULT_LIST}\n  - GITHUB_APP_INSTALLATION_ID"
[ "$GITHUB_CLIENT_ID" = "Iv1.xxxxxxxxxxxx" ] && DEFAULTS_FOUND=true && DEFAULT_LIST="${DEFAULT_LIST}\n  - GITHUB_CLIENT_ID"
[ "$GITHUB_CLIENT_SECRET" = "xxxxxxxxxxxxxxxxxxxx" ] && DEFAULTS_FOUND=true && DEFAULT_LIST="${DEFAULT_LIST}\n  - GITHUB_CLIENT_SECRET"
[ "$GITHUB_ORG" = "your-org-name" ] && DEFAULTS_FOUND=true && DEFAULT_LIST="${DEFAULT_LIST}\n  - GITHUB_ORG"
[ "$DEVPULSE_INITIAL_ADMIN" = "your-github-username" ] && DEFAULTS_FOUND=true && DEFAULT_LIST="${DEFAULT_LIST}\n  - DEVPULSE_INITIAL_ADMIN"
[ "$FRONTEND_URL" = "https://devpulse.yourdomain.com" ] && DEFAULTS_FOUND=true && DEFAULT_LIST="${DEFAULT_LIST}\n  - FRONTEND_URL"
if $DEFAULTS_FOUND; then
    echo "WARNING: Some values were left as defaults. Edit $OUTPUT_FILE to set:"
    echo -e "$DEFAULT_LIST"
    echo ""
fi
if [ "$ENCRYPTION_KEY" = "GENERATE_ME_WITH_FERNET" ]; then
    echo "ACTION REQUIRED: Generate ENCRYPTION_KEY and update $OUTPUT_FILE:"
    echo "  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    echo ""
fi
echo "Next steps:"
echo "  1. Upload your GitHub App .pem file:"
echo "     scp github-app.pem root@<server>:/etc/devpulse/github-app.pem"
echo "     chmod 600 /etc/devpulse/github-app.pem"
echo ""
echo "  2. Set the GITHUB_WEBHOOK_SECRET shown above in your GitHub App settings:"
echo "     https://github.com/organizations/$GITHUB_ORG/settings/apps"
echo ""
echo "  3. Configure Caddy: edit /etc/caddy/Caddyfile"
echo ""
echo "  4. First deploy:"
echo "     cd /opt/devpulse"
echo "     docker compose -f docker-compose.yml up -d db"
echo "     docker compose -f docker-compose.yml run --rm backend alembic upgrade head"
echo "     docker compose -f docker-compose.yml up -d"
