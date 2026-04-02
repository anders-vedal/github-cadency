#!/usr/bin/env bash
# =============================================================
# DevPulse Server Bootstrap
# Run ONCE on a fresh Ubuntu 24.04 server as root.
#
# What it does:
#   1. Installs Docker Engine + Docker Compose v2
#   2. Installs Caddy reverse proxy
#   3. Creates a 'deploy' user with Docker access
#   4. Creates all directories with correct ownership
#   5. Sets up the deploy SSH key (if provided)
#
# Usage:
#   # Basic (interactive — prompts for deploy public key):
#   ./server-bootstrap.sh
#
#   # Non-interactive (pass public key as argument):
#   ./server-bootstrap.sh "ssh-ed25519 AAAA... deploy-ci"
#
#   # With extra app directories:
#   EXTRA_APPS="recruitment claros" ./server-bootstrap.sh
# =============================================================

set -euo pipefail

# --- Configuration ---
DEPLOY_USER="deploy"
APP_NAME="devpulse"
BACKUP_DIR="/backups"

# Extra apps to create directories for (space-separated)
EXTRA_APPS="${EXTRA_APPS:-}"

# Deploy public key (from argument or interactive prompt)
DEPLOY_PUBKEY="${1:-}"

# --- Pre-flight checks ---
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root."
    echo "Usage: sudo ./server-bootstrap.sh"
    exit 1
fi

if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "Detected OS: $PRETTY_NAME"
else
    echo "WARNING: Could not detect OS. This script is designed for Ubuntu/Debian."
fi

echo "============================================="
echo "  DevPulse Server Bootstrap"
echo "============================================="
echo ""

# --- Step 1: Install Docker ---
echo "--- [1/5] Installing Docker ---"
if command -v docker &> /dev/null; then
    echo "Docker is already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    echo "Docker installed: $(docker --version)"
fi

# Verify Docker Compose v2
if docker compose version &> /dev/null; then
    echo "Docker Compose: $(docker compose version --short)"
else
    echo "ERROR: Docker Compose v2 not found. It should be included with Docker Engine."
    echo "Try: apt install docker-compose-plugin"
    exit 1
fi

# --- Step 2: Install Caddy ---
echo ""
echo "--- [2/5] Installing Caddy ---"
if command -v caddy &> /dev/null; then
    echo "Caddy is already installed: $(caddy version)"
else
    apt install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt update
    apt install -y caddy
    echo "Caddy installed: $(caddy version)"
fi

# --- Step 3: Create deploy user ---
echo ""
echo "--- [3/5] Creating deploy user ---"
if id "$DEPLOY_USER" &> /dev/null; then
    echo "User '$DEPLOY_USER' already exists."
else
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
    echo "User '$DEPLOY_USER' created."
fi

# Ensure docker group membership
if groups "$DEPLOY_USER" | grep -q '\bdocker\b'; then
    echo "User '$DEPLOY_USER' is already in the docker group."
else
    usermod -aG docker "$DEPLOY_USER"
    echo "Added '$DEPLOY_USER' to the docker group."
fi

# --- Step 4: Create directories ---
echo ""
echo "--- [4/5] Creating directories ---"

ALL_APPS="$APP_NAME"
if [ -n "$EXTRA_APPS" ]; then
    ALL_APPS="$APP_NAME $EXTRA_APPS"
fi

for app in $ALL_APPS; do
    # App code directory
    if [ ! -d "/opt/$app" ]; then
        mkdir -p "/opt/$app"
        chown "$DEPLOY_USER:$DEPLOY_USER" "/opt/$app"
        echo "Created /opt/$app"
    else
        echo "/opt/$app already exists"
    fi

    # Config/secrets directory
    if [ ! -d "/etc/$app" ]; then
        mkdir -p "/etc/$app"
        chown "$DEPLOY_USER:$DEPLOY_USER" "/etc/$app"
        echo "Created /etc/$app"
    else
        echo "/etc/$app already exists"
    fi

    # Pre-create .pem placeholder with restrictive permissions
    # so that scp overwrites it instead of creating a world-readable file
    PEM_FILE="/etc/$app/github-app.pem"
    if [ ! -f "$PEM_FILE" ]; then
        install -m 600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /dev/null "$PEM_FILE"
        echo "Created $PEM_FILE (placeholder, chmod 600)"
    fi
done

# Backup directory
if [ ! -d "$BACKUP_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$BACKUP_DIR"
    echo "Created $BACKUP_DIR"
else
    echo "$BACKUP_DIR already exists"
fi

# --- Step 5: Set up deploy SSH key ---
echo ""
echo "--- [5/5] Setting up deploy SSH key ---"

DEPLOY_HOME=$(getent passwd "$DEPLOY_USER" | cut -d: -f6)
SSH_DIR="$DEPLOY_HOME/.ssh"
AUTH_KEYS="$SSH_DIR/authorized_keys"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$SSH_DIR"

if [ -z "$DEPLOY_PUBKEY" ]; then
    echo ""
    echo "Paste the deploy PUBLIC key (from ~/.ssh/deploy_key.pub on your local machine)."
    echo "This key is used by GitHub Actions CI/CD to deploy."
    echo "Press Enter on an empty line to skip."
    echo ""
    read -r -p "> " DEPLOY_PUBKEY
fi

if [ -n "$DEPLOY_PUBKEY" ]; then
    if grep -qF "$DEPLOY_PUBKEY" "$AUTH_KEYS" 2>/dev/null; then
        echo "Deploy key is already in authorized_keys."
    else
        echo "$DEPLOY_PUBKEY" >> "$AUTH_KEYS"
        chmod 600 "$AUTH_KEYS"
        chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH_KEYS"
        echo "Deploy key added to $AUTH_KEYS"
    fi
else
    echo "Skipped — you can add the deploy key later:"
    echo "  echo 'ssh-ed25519 AAAA...' >> $AUTH_KEYS"
fi

# --- Done ---
echo ""
echo "============================================="
echo "  Bootstrap complete!"
echo "============================================="
echo ""
echo "Installed:"
echo "  Docker:  $(docker --version)"
echo "  Compose: $(docker compose version --short)"
echo "  Caddy:   $(caddy version)"
echo ""
echo "User: $DEPLOY_USER (in docker group)"
echo ""
echo "Directories created:"
for app in $ALL_APPS; do
    echo "  /opt/$app   (app code)"
    echo "  /etc/$app   (secrets)"
done
echo "  $BACKUP_DIR      (database backups)"
echo ""
echo "Next steps:"
echo "  1. Clone repo:     su - $DEPLOY_USER -c 'git clone <repo-url> /opt/$APP_NAME'"
echo "  2. Generate .env:  su - $DEPLOY_USER -c 'cd /opt/$APP_NAME && ./scripts/generate-env.sh'"
echo "  3. Upload PEM:     scp github-app.pem root@<server>:/etc/$APP_NAME/github-app.pem"
echo "  4. Configure Caddy: edit /etc/caddy/Caddyfile (see docs/HETZNER-SETUP.md)"
echo "  5. First deploy:   su - $DEPLOY_USER -c 'cd /opt/$APP_NAME && ./scripts/deploy.sh'"
