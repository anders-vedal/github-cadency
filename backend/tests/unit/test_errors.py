"""Tests for the Nordlabs error handling convention (libs/errors.py)."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.libs.errors import (
    BufferedError,
    CadencyErrorClassifier,
    ClassifiedError,
    ErrorCategory,
    ErrorClassifier,
    ErrorReporter,
    ErrorSanitizer,
    ErrorSignature,
    _CATEGORY_STATUS,
    _derive_component,
)


# ---------------------------------------------------------------------------
# ErrorClassifier — base rules
# ---------------------------------------------------------------------------


class TestErrorClassifierBase:
    def setup_method(self):
        self.classifier = ErrorClassifier()

    def test_http_401_user_auth(self):
        result = self.classifier.classify(Exception(), http_status=401)
        assert result.category == ErrorCategory.USER_AUTH
        assert result.user_fixable is True

    def test_http_403_user_permission(self):
        result = self.classifier.classify(Exception(), http_status=403)
        assert result.category == ErrorCategory.USER_PERMISSION

    def test_http_400_user_input(self):
        result = self.classifier.classify(Exception(), http_status=400)
        assert result.category == ErrorCategory.USER_INPUT

    def test_http_422_user_input(self):
        result = self.classifier.classify(Exception(), http_status=422)
        assert result.category == ErrorCategory.USER_INPUT

    def test_http_429_rate_limited(self):
        result = self.classifier.classify(Exception(), http_status=429)
        assert result.category == ErrorCategory.RATE_LIMITED

    def test_http_502_transient(self):
        result = self.classifier.classify(Exception(), http_status=502)
        assert result.category == ErrorCategory.TRANSIENT

    def test_http_503_transient(self):
        result = self.classifier.classify(Exception(), http_status=503)
        assert result.category == ErrorCategory.TRANSIENT

    def test_http_500_app_bug(self):
        result = self.classifier.classify(Exception(), http_status=500)
        assert result.category == ErrorCategory.APP_BUG

    def test_permission_error(self):
        result = self.classifier.classify(PermissionError("denied"))
        assert result.category == ErrorCategory.USER_PERMISSION

    def test_value_error(self):
        result = self.classifier.classify(ValueError("bad"))
        assert result.category == ErrorCategory.USER_INPUT

    def test_connection_error(self):
        result = self.classifier.classify(ConnectionError("refused"))
        assert result.category == ErrorCategory.TRANSIENT

    def test_timeout_error(self):
        result = self.classifier.classify(TimeoutError("timed out"))
        assert result.category == ErrorCategory.TRANSIENT

    def test_unknown_exception_is_app_bug(self):
        result = self.classifier.classify(RuntimeError("unexpected"))
        assert result.category == ErrorCategory.APP_BUG
        assert result.user_fixable is False


# ---------------------------------------------------------------------------
# CadencyErrorClassifier — GitHub + AI rules
# ---------------------------------------------------------------------------


class TestCadencyErrorClassifier:
    def setup_method(self):
        self.classifier = CadencyErrorClassifier()

    def _make_http_error(self, status_code: int, headers: dict | None = None) -> httpx.HTTPStatusError:
        response = httpx.Response(
            status_code=status_code,
            headers=headers or {},
            request=httpx.Request("GET", "https://api.github.com/test"),
        )
        return httpx.HTTPStatusError("error", request=response.request, response=response)

    def test_github_rate_limit_403(self):
        exc = self._make_http_error(403, {"X-RateLimit-Remaining": "0"})
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.RATE_LIMITED

    def test_github_secondary_rate_limit(self):
        exc = self._make_http_error(403, {"Retry-After": "60"})
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.RATE_LIMITED

    def test_github_403_without_rate_limit_is_permission(self):
        exc = self._make_http_error(403)
        # Falls through GitHub rules to base HTTP status rules
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.USER_PERMISSION

    def test_github_5xx_provider(self):
        exc = self._make_http_error(500)
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.PROVIDER

    def test_github_502_provider(self):
        exc = self._make_http_error(502)
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.PROVIDER

    def test_github_401_user_config(self):
        exc = self._make_http_error(401)
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.USER_CONFIG

    def test_github_404_user_config(self):
        exc = self._make_http_error(404)
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.USER_CONFIG

    def test_ai_disabled_error(self):
        from app.services.exceptions import AIFeatureDisabledError

        exc = AIFeatureDisabledError("AI is off")
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.USER_CONFIG
        assert result.user_fixable is True
        assert result.user_message == "AI is off"

    def test_ai_budget_error(self):
        from app.services.exceptions import AIBudgetExceededError

        exc = AIBudgetExceededError("Budget blown")
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.RATE_LIMITED
        assert result.user_fixable is True

    def test_app_rules_checked_before_base(self):
        """GitHub 401 should be USER_CONFIG (app rule), not USER_AUTH (base rule)."""
        exc = self._make_http_error(401)
        result = self.classifier.classify(exc)
        assert result.category == ErrorCategory.USER_CONFIG  # app rule wins


# ---------------------------------------------------------------------------
# ErrorSanitizer
# ---------------------------------------------------------------------------


class TestErrorSanitizer:
    def setup_method(self):
        self.sanitizer = ErrorSanitizer()

    def test_email_redacted(self):
        assert "[EMAIL]" in self.sanitizer.sanitize("Error for user@example.com")

    def test_bearer_token_redacted(self):
        assert "[CREDENTIAL]" in self.sanitizer.sanitize("Bearer sk-ant-abc123xyz")

    def test_api_key_redacted(self):
        assert "[CREDENTIAL]" in self.sanitizer.sanitize("api_key=super_secret_123")

    def test_windows_path_redacted(self):
        assert "[USER_PATH]" in self.sanitizer.sanitize(r"Error at C:\Users\john\project\file.py")

    def test_unix_path_redacted(self):
        assert "[USER_PATH]" in self.sanitizer.sanitize("Error at /home/jane/project/file.py")

    def test_uuid_redacted(self):
        assert "[UUID]" in self.sanitizer.sanitize("Record 550e8400-e29b-41d4-a716-446655440000 not found")

    def test_password_redacted(self):
        assert "[REDACTED]" in self.sanitizer.sanitize('password="hunter2"')

    def test_secret_redacted(self):
        assert "[REDACTED]" in self.sanitizer.sanitize("secret=my_secret_value")

    def test_truncation(self):
        long_msg = "x" * 1000
        assert len(self.sanitizer.sanitize(long_msg)) == 500

    def test_clean_message_unchanged(self):
        msg = "Something went wrong in module foo"
        assert self.sanitizer.sanitize(msg) == msg


# ---------------------------------------------------------------------------
# ErrorSignature
# ---------------------------------------------------------------------------


class TestErrorSignature:
    def test_deterministic_key(self):
        sig1 = ErrorSignature("apis.sync", "ValueError", "/api/sync")
        sig2 = ErrorSignature("apis.sync", "ValueError", "/api/sync")
        assert sig1.key == sig2.key

    def test_different_component_different_key(self):
        sig1 = ErrorSignature("apis.sync", "ValueError", "/api/sync")
        sig2 = ErrorSignature("apis.stats", "ValueError", "/api/sync")
        assert sig1.key != sig2.key

    def test_key_length(self):
        sig = ErrorSignature("apis.sync", "ValueError", "/api/sync")
        assert len(sig.key) == 16

    def test_none_endpoint(self):
        sig = ErrorSignature("apis.sync", "ValueError", None)
        assert len(sig.key) == 16


# ---------------------------------------------------------------------------
# ErrorReporter
# ---------------------------------------------------------------------------


class TestErrorReporter:
    def _make_reporter(self, **kwargs) -> ErrorReporter:
        defaults = {
            "sentinel_url": "https://sentinel.example.com",
            "sentinel_secret": "test-secret",
            "app_id": "github-cadency",
            "app_version": "0.1.0",
            "environment": "production",
            "source_id": "test-org",
            "threshold_frequency": 3,
            "threshold_window_seconds": 3600,
        }
        defaults.update(kwargs)
        return ErrorReporter(**defaults)

    def test_enabled_in_production(self):
        reporter = self._make_reporter()
        assert reporter.enabled is True

    def test_disabled_without_url(self):
        reporter = self._make_reporter(sentinel_url="")
        assert reporter.enabled is False

    def test_disabled_without_secret(self):
        reporter = self._make_reporter(sentinel_secret="")
        assert reporter.enabled is False

    def test_disabled_in_development(self):
        reporter = self._make_reporter(environment="development")
        assert reporter.enabled is False

    def test_record_increments_frequency(self):
        reporter = self._make_reporter()
        exc = RuntimeError("test")
        reporter.record(exc, component="apis.test", endpoint_path="/api/test")
        reporter.record(exc, component="apis.test", endpoint_path="/api/test")

        assert len(reporter._buffer) == 1
        entry = next(iter(reporter._buffer.values()))
        assert entry.frequency == 2

    def test_record_separate_entries_for_different_errors(self):
        reporter = self._make_reporter()
        reporter.record(RuntimeError("a"), component="apis.test", endpoint_path="/api/test")
        reporter.record(ValueError("b"), component="apis.test", endpoint_path="/api/test")
        assert len(reporter._buffer) == 2

    def test_record_noop_when_disabled(self):
        reporter = self._make_reporter(environment="development")
        reporter.record(RuntimeError("test"), component="apis.test")
        assert len(reporter._buffer) == 0

    @pytest.mark.asyncio
    async def test_flush_sends_all_buffered_errors(self):
        reporter = self._make_reporter()
        exc = RuntimeError("test")
        reporter.record(exc, component="apis.test", endpoint_path="/api/test")
        reporter.record(exc, component="apis.test", endpoint_path="/api/test")

        with patch.object(reporter, "_send", new_callable=AsyncMock) as mock_send:
            await reporter.flush()
            mock_send.assert_called_once()
            reports = mock_send.call_args[0][0]
            assert len(reports) == 1
            assert reports[0]["frequency"] == 2
            assert reports[0]["component"] == "apis.test"

    @pytest.mark.asyncio
    async def test_flush_sends_single_occurrence(self):
        reporter = self._make_reporter()
        reporter.record(RuntimeError("test"), component="apis.test")

        with patch.object(reporter, "_send", new_callable=AsyncMock) as mock_send:
            await reporter.flush()
            mock_send.assert_called_once()
            reports = mock_send.call_args[0][0]
            assert len(reports) == 1
            assert reports[0]["frequency"] == 1

    @pytest.mark.asyncio
    async def test_flush_includes_trigger_type(self):
        reporter = self._make_reporter()
        reporter.record(RuntimeError("test"), component="apis.test", trigger_type="scheduled")

        with patch.object(reporter, "_send", new_callable=AsyncMock) as mock_send:
            await reporter.flush()
            reports = mock_send.call_args[0][0]
            assert reports[0]["trigger_type"] == "scheduled"

    @pytest.mark.asyncio
    async def test_flush_clears_buffer(self):
        reporter = self._make_reporter()
        reporter.record(RuntimeError("test"), component="apis.test")

        with patch.object(reporter, "_send", new_callable=AsyncMock):
            await reporter.flush()
        assert len(reporter._buffer) == 0

    @pytest.mark.asyncio
    async def test_flush_noop_when_disabled(self):
        reporter = self._make_reporter(environment="development")
        with patch.object(reporter, "_send", new_callable=AsyncMock) as mock_send:
            await reporter.flush()
            mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# _derive_component
# ---------------------------------------------------------------------------


class TestDeriveComponent:
    def _request(self, path: str):
        from unittest.mock import MagicMock
        req = MagicMock()
        req.url.path = path
        return req

    def test_api_path(self):
        assert _derive_component(self._request("/api/stats/benchmarks")) == "apis.stats"

    def test_api_root(self):
        assert _derive_component(self._request("/api/health")) == "apis.health"

    def test_non_api_path(self):
        assert _derive_component(self._request("/metrics")) == "apis.metrics"

    def test_empty_path(self):
        assert _derive_component(self._request("/")) == "apis.unknown"


# ---------------------------------------------------------------------------
# Category → HTTP status mapping completeness
# ---------------------------------------------------------------------------


class TestCategoryStatusMapping:
    def test_all_categories_have_status(self):
        for cat in ErrorCategory:
            assert cat in _CATEGORY_STATUS, f"Missing status for {cat}"
