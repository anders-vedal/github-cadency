"""Rate limiting configuration using slowapi."""

from fastapi import Request
from slowapi import Limiter

from app.config import settings


def _get_remote_address(request: Request) -> str:
    """Extract client IP from X-Forwarded-For (proxy-aware) or fall back to client host."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(
    key_func=_get_remote_address,
    default_limits=["120/minute"],
    enabled=settings.rate_limit_enabled,
)
