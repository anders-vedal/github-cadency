"""Slack integration service — configuration, notification sending, and scheduled jobs."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging import get_logger
from app.models.models import (
    Developer,
    NotificationLog,
    PullRequest,
    SlackConfig,
    SlackUserSettings,
    SyncEvent,
)
from app.schemas.schemas import SlackConfigUpdate, SlackUserSettingsUpdate
from app.services.encryption import decrypt_token, encrypt_token

logger = get_logger(__name__)


# --- Config CRUD ---


async def get_slack_config(db: AsyncSession) -> SlackConfig:
    """Get the singleton Slack config row. Creates default if missing."""
    row = await db.get(SlackConfig, 1)
    if not row:
        row = SlackConfig(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def update_slack_config(
    db: AsyncSession, updates: SlackConfigUpdate, updated_by: str
) -> SlackConfig:
    """Partial update of Slack config. Returns updated row."""
    row = await get_slack_config(db)

    for field, value in updates.model_dump(exclude_unset=True).items():
        if field == "bot_token" and value:
            value = encrypt_token(value)
        setattr(row, field, value)

    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = updated_by
    await db.commit()
    await db.refresh(row)
    return row


def get_decrypted_bot_token(config: SlackConfig) -> str | None:
    """Return the decrypted bot token, or None if not configured."""
    if not config.bot_token:
        return None
    try:
        return decrypt_token(config.bot_token)
    except ValueError:
        logger.warning(
            "Failed to decrypt Slack bot token",
            error_category="user_config",
            event_type="system.slack",
        )
        return None


def build_config_response(config: SlackConfig) -> dict:
    """Build SlackConfigResponse dict from ORM object (never expose bot_token)."""
    return {
        c.key: getattr(config, c.key)
        for c in SlackConfig.__table__.columns
        if c.key not in ("id", "bot_token")
    } | {"bot_token_configured": bool(config.bot_token)}


# --- User Settings CRUD ---


async def get_slack_user_settings(
    db: AsyncSession, developer_id: int
) -> SlackUserSettings:
    """Get or create per-developer Slack settings."""
    result = await db.execute(
        select(SlackUserSettings).where(
            SlackUserSettings.developer_id == developer_id
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        try:
            row = SlackUserSettings(developer_id=developer_id)
            db.add(row)
            await db.commit()
            await db.refresh(row)
        except IntegrityError:
            await db.rollback()
            result = await db.execute(
                select(SlackUserSettings).where(
                    SlackUserSettings.developer_id == developer_id
                )
            )
            row = result.scalar_one()
    return row


async def update_slack_user_settings(
    db: AsyncSession, developer_id: int, updates: SlackUserSettingsUpdate
) -> SlackUserSettings:
    """Partial update of a developer's Slack preferences."""
    row = await get_slack_user_settings(db, developer_id)
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


# --- Slack API helpers ---


def _get_client(bot_token: str) -> AsyncWebClient:
    return AsyncWebClient(token=bot_token)


async def _send_message(
    bot_token: str,
    channel: str,
    text: str,
    blocks: list[dict] | None = None,
) -> dict:
    """Send a Slack message. Returns API response or raises."""
    client = _get_client(bot_token)
    response = await client.chat_postMessage(
        channel=channel,
        text=text,
        blocks=blocks,
    )
    return {"ok": response["ok"], "ts": response.get("ts")}


async def _log_notification(
    db: AsyncSession,
    notification_type: str,
    channel: str | None,
    developer_id: int | None,
    status: str,
    error_message: str | None = None,
    payload: dict | None = None,
) -> None:
    """Write a notification_log entry."""
    entry = NotificationLog(
        notification_type=notification_type,
        channel=channel,
        recipient_developer_id=developer_id,
        status=status,
        error_message=error_message,
        payload=payload,
    )
    db.add(entry)
    await db.commit()


# --- Guard ---


async def _check_slack_enabled(db: AsyncSession) -> tuple[SlackConfig, str]:
    """Verify Slack is enabled and has a bot token.

    Returns (config, decrypted_bot_token) or raises.
    """
    config = await get_slack_config(db)
    if not config.slack_enabled:
        raise HTTPException(403, "Slack notifications are disabled.")
    if not config.bot_token:
        raise HTTPException(503, "Slack bot token is not configured.")
    token = get_decrypted_bot_token(config)
    if not token:
        raise HTTPException(503, "Slack bot token could not be decrypted.")
    return config, token


# --- Test connection ---


async def send_test_message(db: AsyncSession) -> dict:
    """Send a test message to the default channel (or DM to caller)."""
    config, bot_token = await _check_slack_enabled(db)
    channel = config.default_channel
    if not channel:
        # Try auth.test to at least verify the token
        try:
            client = _get_client(bot_token)
            auth = await client.auth_test()
            return {"success": True, "message": f"Connected as {auth['user']} to {auth['team']}. No default channel set."}
        except SlackApiError as e:
            return {"success": False, "message": f"Token invalid: {e.response['error']}"}

    try:
        await _send_message(
            bot_token,
            channel,
            "DevPulse test notification — Slack integration is working.",
        )
        await _log_notification(db, "test", channel, None, "sent")
        return {"success": True, "message": f"Test message sent to {channel}"}
    except SlackApiError as e:
        error = e.response["error"]
        await _log_notification(db, "test", channel, None, "failed", error_message=error)
        return {"success": False, "message": f"Failed: {error}"}


# --- Notification history ---


async def get_notification_history(
    db: AsyncSession, limit: int = 50, offset: int = 0
) -> tuple[list[NotificationLog], int]:
    """Get notification history with count."""
    total = (
        await db.execute(select(func.count()).select_from(NotificationLog))
    ).scalar_one()

    result = await db.execute(
        select(NotificationLog)
        .order_by(NotificationLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all(), total


# --- Notification senders ---


async def _send_dm_to_developer(
    db: AsyncSession,
    bot_token: str,
    developer: Developer,
    notification_type: str,
    text: str,
    blocks: list[dict] | None = None,
) -> bool:
    """Send a DM to a developer if they have a Slack user ID and the notification enabled."""
    user_settings = await get_slack_user_settings(db, developer.id)
    if not user_settings.slack_user_id:
        return False

    # Check per-user toggle
    toggle_attr = f"notify_{notification_type}s" if notification_type == "stale_pr" else f"notify_{notification_type}"
    # Normalize toggle attribute name
    toggle_map = {
        "stale_pr": "notify_stale_prs",
        "high_risk_pr": "notify_high_risk_prs",
        "workload": "notify_workload_alerts",
        "weekly_digest": "notify_weekly_digest",
    }
    toggle = toggle_map.get(notification_type)
    if toggle and not getattr(user_settings, toggle, True):
        return False

    try:
        await _send_message(bot_token, user_settings.slack_user_id, text, blocks)
        await _log_notification(
            db, notification_type, user_settings.slack_user_id, developer.id, "sent",
            payload={"text": text[:200]},
        )
        return True
    except SlackApiError as e:
        error = e.response["error"]
        logger.warning("Failed to DM", github_username=developer.github_username, error=error, event_type="system.slack")
        await _log_notification(
            db, notification_type, user_settings.slack_user_id, developer.id, "failed",
            error_message=error, payload={"text": text[:200]},
        )
        return False


async def send_stale_pr_nudges(db: AsyncSession) -> int:
    """Daily job: find stale open PRs and DM their authors."""
    config = await get_slack_config(db)
    if not config.slack_enabled or not config.bot_token or not config.notify_stale_prs:
        return 0
    bot_token = get_decrypted_bot_token(config)
    if not bot_token:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=config.stale_pr_days_threshold)

    result = await db.execute(
        select(PullRequest)
        .where(
            PullRequest.state == "open",
            PullRequest.is_draft.isnot(True),
            PullRequest.created_at <= cutoff,
            PullRequest.author_id.isnot(None),
        )
    )
    stale_prs = result.scalars().all()
    if not stale_prs:
        return 0

    # Group by author
    author_prs: dict[int, list[PullRequest]] = {}
    for pr in stale_prs:
        author_prs.setdefault(pr.author_id, []).append(pr)

    sent = 0
    for author_id, prs in author_prs.items():
        dev = await db.get(Developer, author_id)
        if not dev or not dev.is_active:
            continue

        pr_lines = []
        for pr in prs[:10]:  # Cap at 10 per message
            created_at = pr.created_at if pr.created_at.tzinfo else pr.created_at.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - created_at).days
            pr_lines.append(f"• *#{pr.number}* {pr.title} ({days}d old)")

        text = f"You have {len(prs)} stale PR{'s' if len(prs) != 1 else ''} open for >{config.stale_pr_days_threshold} days:\n" + "\n".join(pr_lines)
        if await _send_dm_to_developer(db, bot_token, dev, "stale_pr", text):
            sent += 1

    logger.info("Sent stale PR nudges", developers_notified=sent, stale_prs=len(stale_prs), event_type="system.slack")
    return sent


async def send_high_risk_pr_alert(
    db: AsyncSession, pr: PullRequest, risk_score: float
) -> bool:
    """Send alert for a high-risk PR to its author."""
    config = await get_slack_config(db)
    if not config.slack_enabled or not config.bot_token or not config.notify_high_risk_prs:
        return False
    bot_token = get_decrypted_bot_token(config)
    if not bot_token:
        return False
    if risk_score < config.risk_score_threshold:
        return False
    if not pr.author_id:
        return False

    dev = await db.get(Developer, pr.author_id)
    if not dev or not dev.is_active:
        return False

    level = "Critical" if risk_score >= 0.9 else "High"
    text = (
        f"⚠️ *{level}-risk PR detected*\n"
        f"*#{pr.number}* {pr.title}\n"
        f"Risk score: {risk_score:.0%} — "
        f"+{pr.additions or 0}/-{pr.deletions or 0} lines, {pr.changed_files or 0} files"
    )
    return await _send_dm_to_developer(db, bot_token, dev, "high_risk_pr", text)


async def send_workload_alert(
    db: AsyncSession, developer: Developer, workload_score: int, workload_level: str
) -> bool:
    """Send alert when a developer becomes overloaded."""
    config = await get_slack_config(db)
    if not config.slack_enabled or not config.bot_token or not config.notify_workload_alerts:
        return False
    bot_token = get_decrypted_bot_token(config)
    if not bot_token:
        return False

    text = (
        f"Your workload is now *{workload_level}* (score: {workload_score}).\n"
        f"Consider closing or delegating some open items."
    )
    return await _send_dm_to_developer(db, bot_token, developer, "workload", text)


async def send_sync_notification(
    db: AsyncSession, sync_event: SyncEvent
) -> bool:
    """Send sync completion/failure notification to default channel."""
    config = await get_slack_config(db)
    if not config.slack_enabled or not config.bot_token:
        return False
    bot_token = get_decrypted_bot_token(config)
    if not bot_token:
        return False

    is_failure = sync_event.status in ("failed", "completed_with_errors")
    if is_failure and not config.notify_sync_failures:
        return False
    if not is_failure and not config.notify_sync_complete:
        return False

    channel = config.default_channel
    if not channel:
        return False

    completed = len(sync_event.repos_completed or [])
    failed = len(sync_event.repos_failed or [])
    duration = f"{sync_event.duration_s}s" if sync_event.duration_s else "unknown"

    if is_failure:
        text = (
            f"⚠️ *Sync {sync_event.status}*\n"
            f"Type: {sync_event.sync_type} | {completed} repos ok, {failed} failed | Duration: {duration}"
        )
    else:
        text = (
            f"✅ *Sync completed*\n"
            f"Type: {sync_event.sync_type} | {completed} repos synced | Duration: {duration}"
        )

    try:
        await _send_message(bot_token, channel, text)
        await _log_notification(
            db, "sync_failure" if is_failure else "sync_complete",
            channel, None, "sent", payload={"text": text[:200]},
        )
        return True
    except SlackApiError as e:
        error = e.response["error"]
        logger.warning("Failed to send sync notification", error=str(error), event_type="system.slack")
        await _log_notification(
            db, "sync_failure" if is_failure else "sync_complete",
            channel, None, "failed", error_message=error,
        )
        return False


async def send_weekly_digest(db: AsyncSession) -> int:
    """Weekly job: send digest to all subscribed developers."""
    from app.services.stats import get_team_stats

    config = await get_slack_config(db)
    if not config.slack_enabled or not config.bot_token or not config.notify_weekly_digest:
        return 0
    bot_token = get_decrypted_bot_token(config)
    if not bot_token:
        return 0

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    try:
        stats = await get_team_stats(db, team=None, date_from=week_ago, date_to=now)
    except Exception as e:
        logger.warning("Failed to compute weekly digest metrics", error=str(e), event_type="system.slack")
        return 0

    avg_merge = f"{stats.avg_time_to_merge_hours:.1f}h" if stats.avg_time_to_merge_hours else "N/A"
    text = (
        f"📊 *Weekly DevPulse Digest*\n"
        f"Period: {week_ago.strftime('%b %d')} — {now.strftime('%b %d')}\n\n"
        f"• PRs merged: *{stats.total_merged}*\n"
        f"• PRs opened: *{stats.total_prs}*\n"
        f"• Avg time to merge: *{avg_merge}*\n"
        f"• Reviews given: *{stats.total_reviews}*\n"
        f"• Active developers: *{stats.developer_count}*"
    )

    # Send to all developers with weekly digest enabled
    result = await db.execute(
        select(Developer).where(Developer.is_active.is_(True))
    )
    developers = result.scalars().all()

    sent = 0
    for dev in developers:
        if await _send_dm_to_developer(db, bot_token, dev, "weekly_digest", text):
            sent += 1

    logger.info("Sent weekly digest", developers_notified=sent, event_type="system.slack")
    return sent


# --- Scheduled job wrappers (called by APScheduler) ---


async def scheduled_stale_pr_check() -> None:
    """APScheduler entry point for daily stale PR nudges.

    Runs every hour; only sends if current UTC hour matches configured hour.
    """
    from app.models.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            config = await get_slack_config(db)
            if datetime.now(timezone.utc).hour != config.stale_check_hour_utc:
                return
            await send_stale_pr_nudges(db)
        except Exception as e:
            _log_scheduled_error("Stale PR check failed", e, "services.slack")


async def scheduled_weekly_digest() -> None:
    """APScheduler entry point for weekly digest.

    Runs every hour; only sends if current UTC hour and day match configured schedule.
    """
    from app.models.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            config = await get_slack_config(db)
            now = datetime.now(timezone.utc)
            if now.weekday() != config.digest_day_of_week:
                return
            if now.hour != config.digest_hour_utc:
                return
            await send_weekly_digest(db)
        except Exception as e:
            _log_scheduled_error("Weekly digest failed", e, "services.slack")


def _log_scheduled_error(message: str, exc: Exception, component: str) -> None:
    """Classify, log, and report errors from APScheduler-driven Slack jobs."""
    from app.main import _classifier, _reporter

    classified = _classifier.classify(exc)
    log_level = logger.error if classified.category.value == "app_bug" else logger.warning
    log_level(
        message,
        error=str(exc)[:200],
        exc_type=type(exc).__name__,
        error_category=classified.category.value,
        event_type="system.slack",
    )
    if classified.category.value == "app_bug" and _reporter:
        _reporter.record(exc, component=component, trigger_type="scheduled")
