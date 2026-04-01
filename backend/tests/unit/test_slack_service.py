"""Unit tests for Slack service — config, user settings, notification formatting."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Developer, NotificationLog, PullRequest, SlackConfig, SlackUserSettings
from app.services.slack import (
    build_config_response,
    decrypt_token,
    encrypt_token,
    get_decrypted_bot_token,
    get_slack_config,
    get_slack_user_settings,
    send_high_risk_pr_alert,
    send_stale_pr_nudges,
    send_sync_notification,
    send_workload_alert,
    send_test_message,
    update_slack_config,
    update_slack_user_settings,
)
from app.schemas.schemas import SlackConfigUpdate, SlackUserSettingsUpdate


class TestGetSlackConfig:
    @pytest.mark.asyncio
    async def test_creates_default_on_first_access(self, db_session: AsyncSession):
        config = await get_slack_config(db_session)
        assert config.id == 1
        assert config.slack_enabled is False
        assert config.bot_token is None
        assert config.stale_pr_days_threshold == 3
        assert config.risk_score_threshold == 0.7

    @pytest.mark.asyncio
    async def test_returns_existing(self, db_session: AsyncSession):
        # Create first
        config1 = await get_slack_config(db_session)
        config1.slack_enabled = True
        await db_session.commit()

        # Get again
        config2 = await get_slack_config(db_session)
        assert config2.slack_enabled is True
        assert config2.id == 1


class TestUpdateSlackConfig:
    @pytest.mark.asyncio
    async def test_partial_update(self, db_session: AsyncSession):
        updates = SlackConfigUpdate(
            slack_enabled=True,
            bot_token="xoxb-test-token",
            default_channel="#test-channel",
        )
        config = await update_slack_config(db_session, updates, "admin")
        assert config.slack_enabled is True
        # bot_token is stored encrypted — verify it decrypts back to the original
        assert config.bot_token != "xoxb-test-token"  # encrypted, not plaintext
        assert config.bot_token.startswith("gAAAAAB")  # Fernet ciphertext prefix
        assert get_decrypted_bot_token(config) == "xoxb-test-token"
        assert config.default_channel == "#test-channel"
        assert config.updated_by == "admin"

    @pytest.mark.asyncio
    async def test_unset_fields_not_touched(self, db_session: AsyncSession):
        # Set initial values
        await update_slack_config(
            db_session,
            SlackConfigUpdate(stale_pr_days_threshold=5),
            "admin",
        )
        # Update only channel
        config = await update_slack_config(
            db_session,
            SlackConfigUpdate(default_channel="#new"),
            "admin",
        )
        assert config.stale_pr_days_threshold == 5
        assert config.default_channel == "#new"


class TestBuildConfigResponse:
    @pytest.mark.asyncio
    async def test_hides_bot_token(self, db_session: AsyncSession):
        config = await get_slack_config(db_session)
        config.bot_token = "xoxb-secret"
        resp = build_config_response(config)
        assert "bot_token" not in resp
        assert resp["bot_token_configured"] is True

    @pytest.mark.asyncio
    async def test_no_token_configured(self, db_session: AsyncSession):
        config = await get_slack_config(db_session)
        resp = build_config_response(config)
        assert resp["bot_token_configured"] is False


class TestSlackUserSettings:
    @pytest.mark.asyncio
    async def test_creates_default(self, db_session: AsyncSession, sample_developer):
        settings = await get_slack_user_settings(db_session, sample_developer.id)
        assert settings.developer_id == sample_developer.id
        assert settings.slack_user_id is None
        assert settings.notify_stale_prs is True
        assert settings.notify_weekly_digest is True

    @pytest.mark.asyncio
    async def test_update_settings(self, db_session: AsyncSession, sample_developer):
        settings = await update_slack_user_settings(
            db_session,
            sample_developer.id,
            SlackUserSettingsUpdate(slack_user_id="U123456", notify_stale_prs=False),
        )
        assert settings.slack_user_id == "U123456"
        assert settings.notify_stale_prs is False
        assert settings.notify_high_risk_prs is True  # unchanged


class TestSendHighRiskPrAlert:
    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, db_session, sample_pr):
        config = await get_slack_config(db_session)
        config.slack_enabled = False
        await db_session.commit()

        result = await send_high_risk_pr_alert(db_session, sample_pr, 0.9)
        assert result is False

    @pytest.mark.asyncio
    async def test_skips_below_threshold(self, db_session, sample_pr):
        config = await get_slack_config(db_session)
        config.slack_enabled = True
        config.bot_token = encrypt_token("xoxb-test")
        config.risk_score_threshold = 0.8
        await db_session.commit()

        result = await send_high_risk_pr_alert(db_session, sample_pr, 0.5)
        assert result is False


class TestTokenEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "xoxb-1234567890-abcdef"
        ciphertext = encrypt_token(plaintext)
        assert ciphertext != plaintext
        assert ciphertext.startswith("gAAAAAB")
        assert decrypt_token(ciphertext) == plaintext

    def test_null_token_returns_none(self, db_session):
        import asyncio

        async def run():
            config = await get_slack_config(db_session)
            assert get_decrypted_bot_token(config) is None

        asyncio.get_event_loop().run_until_complete(run())

    def test_decrypt_invalid_ciphertext_returns_none(self, db_session):
        import asyncio

        async def run():
            config = await get_slack_config(db_session)
            config.bot_token = "not-a-valid-fernet-token"
            assert get_decrypted_bot_token(config) is None

        asyncio.get_event_loop().run_until_complete(run())


class TestSendWorkloadAlert:
    @pytest.mark.asyncio
    async def test_skips_when_disabled(self, db_session, sample_developer):
        config = await get_slack_config(db_session)
        config.slack_enabled = False
        await db_session.commit()

        result = await send_workload_alert(db_session, sample_developer, 15, "overloaded")
        assert result is False
