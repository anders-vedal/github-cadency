"""Regression tests for Linear rate limit handling — HTTP 400 RATELIMITED + 429."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.linear_sync import LinearAPIError, LinearClient


def _mock_response(status_code: int, json_body: dict, headers: dict | None = None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_error = status_code >= 400
    resp.json = MagicMock(return_value=json_body)
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_http_400_ratelimited_is_retried():
    """HTTP 400 with extensions.code=RATELIMITED must trigger a retry, not raise."""
    client = LinearClient("test_key")

    first = _mock_response(
        400,
        {"errors": [{"message": "rate limited", "extensions": {"code": "RATELIMITED"}}]},
        headers={"Retry-After": "1"},
    )
    second = _mock_response(200, {"data": {"viewer": {"id": "u1"}}})

    post_mock = AsyncMock(side_effect=[first, second])
    with patch.object(client._client, "post", post_mock):
        with patch("app.services.linear_sync.asyncio.sleep", new=AsyncMock()):
            result = await client.query("{ viewer { id } }")

    assert result == {"viewer": {"id": "u1"}}
    assert post_mock.call_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_http_429_is_retried():
    """HTTP 429 still triggers a retry with Retry-After backoff."""
    client = LinearClient("test_key")

    first = _mock_response(429, {}, headers={"Retry-After": "2"})
    second = _mock_response(200, {"data": {"x": 1}})

    post_mock = AsyncMock(side_effect=[first, second])
    with patch.object(client._client, "post", post_mock):
        with patch("app.services.linear_sync.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await client.query("{ x }")

    assert result == {"x": 1}
    assert post_mock.call_count == 2
    sleep_mock.assert_called_once()
    await client.close()


@pytest.mark.asyncio
async def test_http_400_non_ratelimit_raises():
    """HTTP 400 without RATELIMITED code still raises LinearAPIError (no retry)."""
    client = LinearClient("test_key")

    resp = _mock_response(
        400,
        {"errors": [{"message": "bad query", "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"}}]},
    )
    post_mock = AsyncMock(return_value=resp)
    with patch.object(client._client, "post", post_mock):
        with pytest.raises(LinearAPIError):
            await client.query("{ bad }")

    # Only one attempt — no retry
    assert post_mock.call_count == 1
    await client.close()


@pytest.mark.asyncio
async def test_proactive_sleep_on_low_complexity_budget():
    """When X-RateLimit-Complexity-Remaining < 10% of limit, client sleeps proactively."""
    client = LinearClient("test_key")

    resp = _mock_response(
        200,
        {"data": {"ok": True}},
        headers={
            "X-RateLimit-Complexity-Remaining": "100000",  # 3.3% of 3M
            "X-RateLimit-Complexity-Limit": "3000000",
            "X-RateLimit-Complexity-Reset": "1",
        },
    )
    post_mock = AsyncMock(return_value=resp)
    with patch.object(client._client, "post", post_mock):
        with patch("app.services.linear_sync.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            await client.query("{ ok }")

    # At least one proactive sleep
    assert sleep_mock.called
    await client.close()


@pytest.mark.asyncio
async def test_no_proactive_sleep_at_healthy_budget():
    """No proactive sleep when ample budget remains."""
    client = LinearClient("test_key")

    resp = _mock_response(
        200,
        {"data": {"ok": True}},
        headers={
            "X-RateLimit-Complexity-Remaining": "2500000",  # 83% remaining
            "X-RateLimit-Complexity-Limit": "3000000",
        },
    )
    post_mock = AsyncMock(return_value=resp)
    with patch.object(client._client, "post", post_mock):
        with patch("app.services.linear_sync.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            await client.query("{ ok }")

    sleep_mock.assert_not_called()
    await client.close()
