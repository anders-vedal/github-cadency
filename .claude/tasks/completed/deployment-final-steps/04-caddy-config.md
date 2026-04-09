# Task 4: Add Caddy Reverse Proxy Config with IP Whitelist

**Status:** done
**Independent** — can be done in parallel with Tasks 1-3

## Problem

DevPulse needs HTTPS termination and IP-level access control. Without a reverse proxy:
- Traffic is unencrypted (JWTs and API tokens sent in plaintext)
- Anyone on the network can reach the app (even behind VPN, the blast radius is the entire VPN)

## Changes Required

### 4a. Create `infrastructure/Caddyfile`

```
# DevPulse reverse proxy
# Handles HTTPS termination + IP whitelist.
#
# Caddy runs on the host (not in Docker) so it persists across deploys.
#
# Install: https://caddyserver.com/docs/install
# Deploy:  sudo cp infrastructure/Caddyfile /etc/caddy/Caddyfile
# Start:   sudo systemctl enable --now caddy
# Reload:  sudo systemctl reload caddy
#
# Replace the domain and IP ranges below with your values.

devpulse.internal.company.com {
    # --- IP Whitelist ---
    # Only allow requests from VPN / office network ranges.
    # Requests from other IPs get a 403.
    #
    # Common private ranges (customize to your network):
    #   10.0.0.0/8       — Class A private (large VPNs)
    #   172.16.0.0/12    — Class B private
    #   192.168.0.0/16   — Class C private (typical office)
    #
    # Example: allow only the 10.10.0.0/16 VPN subnet:
    #   @blocked not remote_ip 10.10.0.0/16
    @blocked not remote_ip 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16
    respond @blocked "Access denied" 403

    # --- Reverse proxy ---
    # API requests → backend container
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # Everything else → frontend container
    handle {
        reverse_proxy localhost:3001
    }
}
```

### Why Caddy runs on the host (not in Docker)

- **TLS persistence:** Caddy manages certificate lifecycle (auto-renewal, ACME challenges). Running it in Docker means losing certs on `docker compose down` or needing extra volume mounts.
- **Deploy independence:** `docker compose down && docker compose up` during deploys doesn't kill HTTPS. Users see a brief blip, not a TLS error.
- **Simplicity:** One `apt install caddy` or `dnf install caddy`, one config file, one systemd service. No Docker networking complexity.

If the team already runs nginx or Traefik, use that instead — the important thing is the IP whitelist + HTTPS, not the specific tool.

### Why IP whitelist at the proxy layer (not in FastAPI)

- **Defense in depth:** Blocked requests never reach the application. No CPU spent parsing headers, validating JWTs, or hitting the database.
- **Separation of concerns:** Security policy lives in infrastructure config, not application code.
- **Performance:** Caddy rejects blocked IPs immediately with zero overhead.

### TLS certificate options

**If the domain is publicly resolvable** (e.g., `devpulse.company.com` has a public DNS A record, even if the IP is private):
- Caddy auto-provisions a Let's Encrypt certificate. Zero config — it just works.

**If the domain is internal-only** (e.g., `devpulse.internal.company.com` has no public DNS):
- Use your company's internal CA. Add to the Caddyfile:
  ```
  tls /etc/caddy/certs/devpulse.crt /etc/caddy/certs/devpulse.key
  ```
- Or use Caddy's built-in self-signed cert (for testing only):
  ```
  tls internal
  ```

## Verification

```bash
# Install Caddy (Ubuntu/Debian)
sudo apt install -y caddy

# Deploy config
sudo cp infrastructure/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy

# Test from allowed IP
curl -s https://devpulse.internal.company.com/api/health
# Should return {"status": "ok"}

# Test from blocked IP (or simulate by temporarily removing your range)
curl -s https://devpulse.internal.company.com/
# Should return "Access denied" with HTTP 403
```
