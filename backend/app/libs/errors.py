"""Nordlabs error handling convention — GitHub Cadency implementation.

Three components:
  1. ErrorClassifier — categorizes exceptions into 8 canonical categories
  2. ErrorSanitizer — strips PII from error messages before external transmission
  3. ErrorReporter — ring buffer with threshold-based reporting to Sentinel

Plus register_error_handlers() to wire global FastAPI exception handlers.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1. Error Classification
# ---------------------------------------------------------------------------


class ErrorCategory(StrEnum):
    """Universal error categories — identical across all Nordlabs projects."""

    USER_AUTH = "user_auth"
    USER_CONFIG = "user_config"
    USER_INPUT = "user_input"
    USER_PERMISSION = "user_permission"
    RATE_LIMITED = "rate_limited"
    TRANSIENT = "transient"
    PROVIDER = "provider"
    APP_BUG = "app_bug"


@dataclass
class ClassifiedError:
    category: ErrorCategory
    user_fixable: bool
    user_message: str | None = None
    remediation: str | None = None


class ErrorClassifier:
    """Base classifier with shared rules for HTTP status codes and common exceptions."""

    def classify(
        self,
        exc: Exception,
        *,
        http_status: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> ClassifiedError:
        for rule in [*self._app_rules(), *self._base_rules()]:
            result = rule(exc, http_status, context)
            if result is not None:
                return result
        return ClassifiedError(
            category=ErrorCategory.APP_BUG,
            user_fixable=False,
            remediation="Unhandled exception — investigate",
        )

    def _app_rules(self) -> list[Callable]:
        return []

    def _base_rules(self) -> list[Callable]:
        return [self._http_status_rules, self._exception_type_rules]

    def _http_status_rules(self, exc: Exception, http_status: int | None, context: dict | None) -> ClassifiedError | None:
        if http_status is None:
            return None
        mapping: dict[int, tuple[ErrorCategory, bool, str]] = {
            400: (ErrorCategory.USER_INPUT, True, "Bad request"),
            401: (ErrorCategory.USER_AUTH, True, "Authentication required"),
            403: (ErrorCategory.USER_PERMISSION, True, "Permission denied"),
            404: (ErrorCategory.USER_INPUT, True, "Not found"),
            422: (ErrorCategory.USER_INPUT, True, "Validation error"),
            429: (ErrorCategory.RATE_LIMITED, False, "Rate limited — retry later"),
        }
        if http_status in mapping:
            cat, fixable, msg = mapping[http_status]
            return ClassifiedError(category=cat, user_fixable=fixable, user_message=msg)
        if 500 <= http_status < 600:
            if http_status in (502, 503, 504):
                return ClassifiedError(category=ErrorCategory.TRANSIENT, user_fixable=False)
            return ClassifiedError(category=ErrorCategory.APP_BUG, user_fixable=False)
        return None

    def _exception_type_rules(self, exc: Exception, http_status: int | None, context: dict | None) -> ClassifiedError | None:
        if isinstance(exc, PermissionError):
            return ClassifiedError(category=ErrorCategory.USER_PERMISSION, user_fixable=True)
        if isinstance(exc, (ValueError, KeyError, TypeError)):
            return ClassifiedError(category=ErrorCategory.USER_INPUT, user_fixable=True)
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return ClassifiedError(category=ErrorCategory.TRANSIENT, user_fixable=False)
        return None


class CadencyErrorClassifier(ErrorClassifier):
    """GitHub Cadency–specific classification rules."""

    def _app_rules(self) -> list[Callable]:
        return [self._linear_api_rules, self._github_api_rules, self._ai_exception_rules, *super()._app_rules()]

    def _github_api_rules(self, exc: Exception, http_status: int | None, context: dict | None) -> ClassifiedError | None:
        if not isinstance(exc, httpx.HTTPStatusError):
            return None

        status = exc.response.status_code
        headers = exc.response.headers

        # GitHub rate limit (403 with X-RateLimit-Remaining: 0)
        if status == 403 and headers.get("X-RateLimit-Remaining") == "0":
            return ClassifiedError(
                category=ErrorCategory.RATE_LIMITED,
                user_fixable=False,
                remediation="GitHub API rate limit hit — wait for reset",
            )

        # GitHub secondary rate limit (403 with Retry-After)
        if status == 403 and "Retry-After" in headers:
            return ClassifiedError(
                category=ErrorCategory.RATE_LIMITED,
                user_fixable=False,
                remediation="GitHub secondary rate limit — back off",
            )

        # GitHub 5xx — provider issue
        if 500 <= status < 600:
            return ClassifiedError(
                category=ErrorCategory.PROVIDER,
                user_fixable=False,
                remediation="GitHub API server error",
            )

        # GitHub 401 — App auth misconfigured
        if status == 401:
            return ClassifiedError(
                category=ErrorCategory.USER_CONFIG,
                user_fixable=True,
                user_message="GitHub App authentication failed — check configuration",
                remediation="Verify GITHUB_APP_ID, private key, and installation ID",
            )

        # GitHub 404 — typically missing permissions or wrong org
        if status == 404:
            return ClassifiedError(
                category=ErrorCategory.USER_CONFIG,
                user_fixable=True,
                user_message="GitHub resource not found — check App permissions and org name",
            )

        # GitHub 403 without rate limit headers — permission issue
        if status == 403:
            return ClassifiedError(
                category=ErrorCategory.USER_PERMISSION,
                user_fixable=True,
                user_message="GitHub API permission denied",
            )

        return None

    def _ai_exception_rules(self, exc: Exception, http_status: int | None, context: dict | None) -> ClassifiedError | None:
        from app.services.exceptions import AIBudgetExceededError, AIFeatureDisabledError

        if isinstance(exc, AIFeatureDisabledError):
            return ClassifiedError(
                category=ErrorCategory.USER_CONFIG,
                user_fixable=True,
                user_message=exc.detail,
            )
        if isinstance(exc, AIBudgetExceededError):
            return ClassifiedError(
                category=ErrorCategory.RATE_LIMITED,
                user_fixable=True,
                user_message=exc.detail,
            )
        return None

    def _linear_api_rules(self, exc: Exception, http_status: int | None, context: dict | None) -> ClassifiedError | None:
        from app.services.linear_sync import LinearAPIError

        # GraphQL-level errors (200 response with errors payload)
        if isinstance(exc, LinearAPIError):
            msg = str(exc).lower()
            if "authentication" in msg or "unauthorized" in msg:
                return ClassifiedError(
                    category=ErrorCategory.USER_CONFIG,
                    user_fixable=True,
                    user_message="Linear API key is invalid — check integration settings",
                    remediation="Verify Linear API key in integration configuration",
                )
            if "rate" in msg and "limit" in msg:
                return ClassifiedError(
                    category=ErrorCategory.RATE_LIMITED,
                    user_fixable=False,
                    remediation="Linear API rate limit — back off",
                )
            return ClassifiedError(
                category=ErrorCategory.PROVIDER,
                user_fixable=False,
                remediation=f"Linear GraphQL error: {str(exc)[:100]}",
            )

        # HTTP-level errors from Linear (httpx.HTTPStatusError with linear.app URL)
        if isinstance(exc, httpx.HTTPStatusError) and "linear.app" in str(exc.request.url):
            status = exc.response.status_code

            if status == 401:
                return ClassifiedError(
                    category=ErrorCategory.USER_CONFIG,
                    user_fixable=True,
                    user_message="Linear API authentication failed — check API key",
                    remediation="Verify Linear API key in integration configuration",
                )

            if status == 429:
                return ClassifiedError(
                    category=ErrorCategory.RATE_LIMITED,
                    user_fixable=False,
                    remediation="Linear API rate limit hit",
                )

            if status == 403:
                return ClassifiedError(
                    category=ErrorCategory.USER_PERMISSION,
                    user_fixable=True,
                    user_message="Linear API permission denied",
                )

            if 500 <= status < 600:
                return ClassifiedError(
                    category=ErrorCategory.PROVIDER,
                    user_fixable=False,
                    remediation="Linear API server error",
                )

        return None


# ---------------------------------------------------------------------------
# 2. Error Sanitizer
# ---------------------------------------------------------------------------


class ErrorSanitizer:
    """Strips PII from error messages before sending to Sentinel."""

    PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"[\w.-]+@[\w.-]+\.\w+"), "[EMAIL]"),
        (re.compile(r"(Bearer |token[=: ]|api[_-]?key[=: ])\S+", re.I), "[CREDENTIAL]"),
        (re.compile(r"[A-Z]:\\Users\\[^\\]+"), "[USER_PATH]"),
        (re.compile(r"/home/[^/]+/"), "/[USER_PATH]/"),
        (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "[UUID]"),
        (re.compile(r'password["\s:=]+\S+', re.I), "password=[REDACTED]"),
        (re.compile(r'secret["\s:=]+\S+', re.I), "secret=[REDACTED]"),
    ]

    def sanitize(self, message: str) -> str:
        for pattern, replacement in self.PATTERNS:
            message = pattern.sub(replacement, message)
        return message[:500]


# ---------------------------------------------------------------------------
# 3. Error Reporter
# ---------------------------------------------------------------------------


@dataclass
class ErrorSignature:
    component: str
    error_code: str
    endpoint_path: str | None

    @property
    def key(self) -> str:
        raw = f"{self.component}:{self.error_code}:{self.endpoint_path or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class BufferedError:
    signature: ErrorSignature
    error_message: str
    http_status: int | None
    request_context: dict | None = None
    frequency: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    trigger_type: str = "request"


class ErrorReporter:
    """Buffers app_bug errors and reports all to Sentinel on each flush."""

    def __init__(
        self,
        sentinel_url: str,
        sentinel_secret: str,
        app_id: str,
        app_version: str = "dev",
        environment: str = "development",
        source_id: str = "",
        threshold_frequency: int = 5,
        threshold_window_seconds: int = 3600,
        flush_interval_seconds: int = 300,
    ) -> None:
        self.sentinel_url = sentinel_url.rstrip("/") if sentinel_url else ""
        self.sentinel_secret = sentinel_secret
        self.app_id = app_id
        self.app_version = app_version
        self.environment = environment
        self.source_id = source_id
        self.threshold_frequency = threshold_frequency
        self.threshold_window_seconds = threshold_window_seconds
        self.flush_interval_seconds = flush_interval_seconds
        self._buffer: dict[str, BufferedError] = {}
        self._sanitizer = ErrorSanitizer()
        self._start_time = time.monotonic()

    @property
    def enabled(self) -> bool:
        return bool(
            self.sentinel_url
            and self.sentinel_secret
            and self.environment in ("prod", "production")
        )

    def _derive_key(self) -> str:
        return hmac.new(
            self.sentinel_secret.encode(),
            self.app_id.encode(),
            hashlib.sha256,
        ).hexdigest()

    def record(
        self,
        exc: Exception,
        *,
        component: str,
        endpoint_path: str | None = None,
        http_status: int | None = None,
        request_context: dict | None = None,
        trigger_type: str = "request",
    ) -> None:
        if not self.enabled:
            return

        sig = ErrorSignature(
            component=component,
            error_code=type(exc).__name__,
            endpoint_path=endpoint_path,
        )
        key = sig.key
        sanitized_msg = self._sanitizer.sanitize(str(exc))

        if key in self._buffer:
            entry = self._buffer[key]
            entry.frequency += 1
            entry.last_seen = time.time()
            if request_context:
                entry.request_context = request_context
        else:
            self._buffer[key] = BufferedError(
                signature=sig,
                error_message=sanitized_msg,
                http_status=http_status,
                request_context=request_context,
                trigger_type=trigger_type,
            )

    async def flush(self) -> None:
        if not self.enabled or not self._buffer:
            return

        reports: list[dict] = []
        for key, entry in self._buffer.items():
            report: dict[str, Any] = {
                "component": entry.signature.component,
                "error_category": "app_bug",
                "error_code": entry.signature.error_code,
                "error_message": entry.error_message,
                "http_status": entry.http_status,
                "endpoint_path": entry.signature.endpoint_path,
                "frequency": entry.frequency,
                "first_seen": _ts(entry.first_seen),
                "last_seen": _ts(entry.last_seen),
                "trigger_type": entry.trigger_type,
            }
            if entry.request_context:
                report["request_context"] = entry.request_context
            reports.append(report)

        self._buffer.clear()

        if reports:
            await self._send(reports)

    async def _send(self, reports: list[dict]) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.sentinel_url}/api/v1/errors",
                    json={
                        "source_id": self.source_id or None,
                        "environment": self.environment,
                        "app_version": self.app_version,
                        "reports": reports,
                    },
                    headers={
                        "Authorization": f"Bearer {self._derive_key()}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Sentinel report failed",
                        status=resp.status_code,
                        event_type="system.sentinel",
                    )
        except Exception as e:
            logger.debug("Sentinel send failed (non-fatal)", error=str(e), event_type="system.sentinel")

    async def _send_heartbeat(self) -> None:
        if not self.enabled:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self.sentinel_url}/api/v1/heartbeat",
                    json={
                        "app_id": self.app_id,
                        "app_version": self.app_version,
                        "environment": self.environment,
                        "buffer_size": len(self._buffer),
                        "uptime_seconds": int(time.monotonic() - self._start_time),
                    },
                    headers={
                        "Authorization": f"Bearer {self._derive_key()}",
                        "Content-Type": "application/json",
                    },
                )
        except Exception:
            pass

    async def periodic_flush(self) -> None:
        while True:
            await asyncio.sleep(self.flush_interval_seconds)
            with contextlib.suppress(Exception):
                await self.flush()
            with contextlib.suppress(Exception):
                await self._send_heartbeat()


def _ts(unix: float) -> str:
    """Unix timestamp → ISO 8601 UTC string."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(unix, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 4. FastAPI Exception Handlers
# ---------------------------------------------------------------------------

_CATEGORY_STATUS: dict[ErrorCategory, int] = {
    ErrorCategory.USER_AUTH: 401,
    ErrorCategory.USER_CONFIG: 503,
    ErrorCategory.USER_INPUT: 400,
    ErrorCategory.USER_PERMISSION: 403,
    ErrorCategory.RATE_LIMITED: 429,
    ErrorCategory.TRANSIENT: 503,
    ErrorCategory.PROVIDER: 502,
    ErrorCategory.APP_BUG: 500,
}


def _derive_component(request: Request) -> str:
    path = request.url.path
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "api":
        return f"apis.{parts[1]}"
    return f"apis.{parts[0] if parts else 'unknown'}"


def _extract_request_context(request: Request, exc: Exception) -> dict:
    """Extract request context for Sentinel reporting."""
    import traceback

    ua = request.headers.get("user-agent", "")
    ctx: dict[str, Any] = {
        "client_ip": request.client.host if request.client else None,
        "user_agent": ua,
        "request_url": str(request.url),
        "request_method": request.method,
        "referer": request.headers.get("referer"),
        "device_type": _parse_device_type(ua),
        "os": _parse_os(ua),
        "browser": _parse_browser(ua),
    }

    # Extract source location from traceback
    if exc.__traceback__:
        frames = traceback.extract_tb(exc.__traceback__)
        if frames:
            last = frames[-1]
            ctx["source_file"] = _to_relative_path(last.filename)
            ctx["source_line"] = last.lineno
            ctx["source_function"] = last.name

    return {k: v for k, v in ctx.items() if v is not None}


def _parse_device_type(ua: str) -> str:
    ua_lower = ua.lower()
    if any(k in ua_lower for k in ("mobile", "android", "iphone")):
        return "mobile"
    if any(k in ua_lower for k in ("tablet", "ipad")):
        return "tablet"
    if any(k in ua_lower for k in ("bot", "crawler", "spider")):
        return "bot"
    return "desktop"


def _parse_browser(ua: str) -> str | None:
    for name in ("Firefox", "Edg", "Chrome", "Safari", "Opera"):
        if name in ua:
            return "Edge" if name == "Edg" else name
    return None


def _parse_os(ua: str) -> str | None:
    for pattern, name in [("Windows", "Windows"), ("Mac OS", "macOS"), ("Linux", "Linux"),
                          ("Android", "Android"), ("iPhone", "iOS"), ("iPad", "iPadOS")]:
        if pattern in ua:
            return name
    return None


def _to_relative_path(filepath: str) -> str:
    """Strip absolute path prefix, keep project-relative path."""
    for marker in ("/app/", "/backend/"):
        idx = filepath.find(marker)
        if idx != -1:
            return filepath[idx + 1:]
    parts = filepath.replace("\\", "/").split("/")
    return "/".join(parts[-3:]) if len(parts) > 3 else filepath


def register_error_handlers(
    app: FastAPI,
    classifier: ErrorClassifier,
    reporter: ErrorReporter | None = None,
) -> None:
    """Register global exception handlers on the FastAPI app."""

    from app.services.exceptions import AIBudgetExceededError, AIFeatureDisabledError

    @app.exception_handler(AIFeatureDisabledError)
    async def _handle_ai_disabled(request: Request, exc: AIFeatureDisabledError) -> JSONResponse:
        logger.info(
            "AI feature disabled",
            path=request.url.path,
            detail=exc.detail,
            error_category=ErrorCategory.USER_CONFIG.value,
            event_type="system.http",
        )
        return JSONResponse(status_code=403, content={"detail": exc.detail})

    @app.exception_handler(AIBudgetExceededError)
    async def _handle_ai_budget(request: Request, exc: AIBudgetExceededError) -> JSONResponse:
        logger.info(
            "AI budget exceeded",
            path=request.url.path,
            detail=exc.detail,
            error_category=ErrorCategory.RATE_LIMITED.value,
            event_type="system.http",
        )
        return JSONResponse(status_code=429, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def _handle_generic(request: Request, exc: Exception) -> JSONResponse:
        classified = classifier.classify(exc)
        status = _CATEGORY_STATUS.get(classified.category, 500)

        log_kwargs: dict[str, Any] = {
            "event_type": "system.http",
            "method": request.method,
            "path": request.url.path,
            "error": str(exc)[:200],
            "exc_type": type(exc).__name__,
            "error_category": classified.category.value,
        }

        if classified.category == ErrorCategory.APP_BUG:
            logger.error("Unhandled exception", **log_kwargs, exc_info=exc)
            if reporter:
                request_context = _extract_request_context(request, exc)
                reporter.record(
                    exc,
                    component=_derive_component(request),
                    endpoint_path=request.url.path,
                    http_status=status,
                    request_context=request_context,
                )
        elif classified.category in (ErrorCategory.PROVIDER, ErrorCategory.TRANSIENT):
            logger.warning("External error", **log_kwargs)
        else:
            logger.info("Handled error", **log_kwargs)

        detail = classified.user_message or (
            str(exc) if classified.user_fixable else "Internal server error"
        )
        return JSONResponse(status_code=status, content={"detail": detail})
