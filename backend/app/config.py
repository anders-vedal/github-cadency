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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

if not settings.jwt_secret:
    logger.warning("JWT_SECRET is not set — authentication will be insecure")
