"""Shared service utilities."""

from datetime import datetime, timedelta, timezone


def default_range(
    date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime, datetime]:
    """Default to last 30 days if date params are None.

    Also normalises naive datetimes to UTC, since asyncpg rejects naive
    datetimes when bound to TIMESTAMPTZ columns.
    """
    if not date_to:
        date_to = datetime.now(timezone.utc)
    elif date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=timezone.utc)
    if not date_from:
        date_from = date_to - timedelta(days=30)
    elif date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=timezone.utc)
    return date_from, date_to
