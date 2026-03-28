from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://devpulse:devpulse@localhost:5432/devpulse"

    # GitHub App
    github_app_id: int = 0
    github_app_private_key_path: str = "./github-app.pem"
    github_app_installation_id: int = 0
    github_webhook_secret: str = ""
    github_org: str = ""

    # Auth (Phase 1 — single admin token)
    devpulse_admin_token: str = ""

    # AI (optional — only needed for AI analysis)
    anthropic_api_key: str = ""

    # Sync scheduling
    sync_interval_minutes: int = 15
    full_sync_cron_hour: int = 2

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
