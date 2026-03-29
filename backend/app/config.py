import logging

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://devpulse:devpulse@localhost:5432/devpulse"

    # GitHub App
    github_app_id: int = 0
    github_app_private_key_path: str = "./github-app.pem"
    github_app_installation_id: int = 0
    github_webhook_secret: str = ""
    github_org: str = ""

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # Auth
    jwt_secret: str = ""
    devpulse_initial_admin: str = ""
    frontend_url: str = "http://localhost:3001"

    # AI (optional — only needed for AI analysis)
    anthropic_api_key: str = ""

    # Sync scheduling
    sync_interval_minutes: int = 15
    full_sync_cron_hour: int = 2

    # DORA metrics
    deploy_workflow_name: str = ""
    deploy_environment: str = "production"
    hotfix_labels: str = "hotfix,urgent,incident"
    hotfix_branch_prefixes: str = "hotfix/"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

if not settings.jwt_secret:
    logger.warning("JWT_SECRET is not set — authentication will be insecure")


def validate_github_config() -> list[dict]:
    """Validate GitHub App configuration and return a list of check results.

    Each result: {field, status: "ok"|"error"|"warn", message}.
    """
    from pathlib import Path

    checks: list[dict] = []

    # github_org
    if not settings.github_org:
        checks.append({
            "field": "GITHUB_ORG",
            "status": "error",
            "message": "GITHUB_ORG is not set. This is required to discover repos and sync data.",
        })
    else:
        checks.append({"field": "GITHUB_ORG", "status": "ok", "message": f"Set to '{settings.github_org}'"})

    # github_app_id
    if settings.github_app_id == 0:
        checks.append({
            "field": "GITHUB_APP_ID",
            "status": "error",
            "message": "GITHUB_APP_ID is not set (defaults to 0). Set it to your GitHub App's numeric ID.",
        })
    else:
        checks.append({"field": "GITHUB_APP_ID", "status": "ok", "message": f"Set to {settings.github_app_id}"})

    # github_app_installation_id
    if settings.github_app_installation_id == 0:
        checks.append({
            "field": "GITHUB_APP_INSTALLATION_ID",
            "status": "error",
            "message": "GITHUB_APP_INSTALLATION_ID is not set (defaults to 0). "
                       "Find it at https://github.com/settings/installations — click your app, "
                       "the ID is in the URL.",
        })
    else:
        checks.append({
            "field": "GITHUB_APP_INSTALLATION_ID",
            "status": "ok",
            "message": f"Set to {settings.github_app_installation_id}",
        })

    # Private key file
    key_path = Path(settings.github_app_private_key_path)
    if not key_path.exists():
        checks.append({
            "field": "GITHUB_APP_PRIVATE_KEY_PATH",
            "status": "error",
            "message": f"Private key file not found at '{key_path.resolve()}'. "
                       f"Download it from your GitHub App settings > Private keys.",
        })
    elif not key_path.is_file():
        checks.append({
            "field": "GITHUB_APP_PRIVATE_KEY_PATH",
            "status": "error",
            "message": f"'{key_path.resolve()}' exists but is not a file.",
        })
    else:
        try:
            content = key_path.read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                checks.append({
                    "field": "GITHUB_APP_PRIVATE_KEY_PATH",
                    "status": "error",
                    "message": f"Private key file at '{key_path.resolve()}' is empty. "
                               f"Re-download the .pem from your GitHub App settings.",
                })
            elif not content.startswith("-----BEGIN"):
                checks.append({
                    "field": "GITHUB_APP_PRIVATE_KEY_PATH",
                    "status": "error",
                    "message": f"Private key file at '{key_path.resolve()}' does not look like a PEM key "
                               f"(expected '-----BEGIN RSA PRIVATE KEY-----' or '-----BEGIN PRIVATE KEY-----'). "
                               f"The file may be corrupted or contain the wrong content.",
                })
            else:
                checks.append({
                    "field": "GITHUB_APP_PRIVATE_KEY_PATH",
                    "status": "ok",
                    "message": f"Found valid PEM file at '{key_path.resolve()}'",
                })
        except PermissionError:
            checks.append({
                "field": "GITHUB_APP_PRIVATE_KEY_PATH",
                "status": "error",
                "message": f"Cannot read '{key_path.resolve()}' — permission denied.",
            })

    # GitHub OAuth (warn only)
    if not settings.github_client_id or not settings.github_client_secret:
        checks.append({
            "field": "GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET",
            "status": "warn",
            "message": "GitHub OAuth credentials not set. Users won't be able to log in via GitHub.",
        })
    else:
        checks.append({
            "field": "GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET",
            "status": "ok",
            "message": "GitHub OAuth credentials configured",
        })

    return checks
