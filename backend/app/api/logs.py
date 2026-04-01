"""Frontend log ingestion endpoint."""

from fastapi import APIRouter, Request, Response, status

from app.logging import get_logger
from app.rate_limit import limiter
from app.schemas.schemas import FrontendLogBatch

router = APIRouter()

logger = get_logger("app.frontend")

MAX_ENTRIES = 50

# Context keys the frontend is known to send
ALLOWED_CONTEXT_KEYS = frozenset({
    # Global error handler in logger.ts
    "filename", "lineno", "colno",
    # Component-level logging
    "component", "action", "page", "stack",
    "error_name", "error_message", "status",
})

# structlog / pipeline fields that must not be overridden by user input
RESERVED_FIELDS = frozenset({
    "event_type", "source", "request_id", "level",
    "logger", "timestamp", "event",
})

ALLOWED_EVENT_TYPES = frozenset({"frontend.error", "frontend.warn", "frontend.info"})


@router.post("/logs/ingest", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def ingest_logs(request: Request, batch: FrontendLogBatch) -> Response:
    """Receive frontend log entries and emit them through the structlog pipeline."""
    for entry in batch.entries[:MAX_ENTRIES]:
        # Skip entries with unknown event types
        if entry.event_type not in ALLOWED_EVENT_TYPES:
            continue

        # Filter context: allowlist keys, strip reserved fields
        raw_ctx = entry.context or {}
        safe_context = {
            k: v for k, v in raw_ctx.items()
            if k in ALLOWED_CONTEXT_KEYS and k not in RESERVED_FIELDS
        }

        log_fn = logger.error if entry.level == "error" else logger.warning
        log_fn(
            entry.message,
            event_type=entry.event_type,
            source="frontend",
            url=entry.url,
            frontend_timestamp=entry.timestamp,
            **safe_context,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
