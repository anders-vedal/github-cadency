# Add request_context to Sentinel Error Reports

**Status:** Completed
**Priority:** Medium
**Scope:** `backend/app/libs/errors.py`

## Background

Sentinel now accepts an optional `request_context` object on each error report. This provides rich context about where and how errors are triggered — device type, browser, OS, triggering URL, and source code location. Sentinel sanitizes this data server-side (masks IPs, strips URL query params) before storage.

The aggregate detail page in Sentinel now shows:
- **Context summary** — device/browser/OS/URL breakdowns across all occurrences
- **Per-event context** — device, browser, and source location with GitHub permalink for each event
- **Project badge** — which app the error belongs to

## What to Change

### 1. Add request context extraction

**File:** `backend/app/libs/errors.py`

Add a helper function near the existing `_derive_component()` function (around line 493):

```python
def _extract_request_context(request: Request, exc: Exception) -> dict:
    """Extract request context for Sentinel reporting."""
    import traceback

    ua = request.headers.get("user-agent", "")
    ctx = {
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
```

### 2. Update ErrorReporter.record() to accept request_context

**File:** `backend/app/libs/errors.py`

Add `request_context: dict | None = None` parameter to the `record()` method. Store it on the buffered error and include it in the payload.

In the payload construction (around line 393-403), add to each report dict:

```python
"request_context": error.request_context,
```

### 3. Wire it up in the exception handlers

In `register_error_handlers()` (same file, around line 530-560), update the unhandled exception handler to extract and pass context:

```python
request_context = _extract_request_context(request, exc)
reporter.record(
    component=component,
    error_code=type(exc).__name__,
    error_message=str(exc),
    http_status=500,
    endpoint_path=request.url.path,
    request_context=request_context,
)
```

## Sentinel Request Context Schema

All fields are optional. Sentinel sanitizes server-side (masks IPs, strips URL query params), but avoid sending raw PII like user IDs or email addresses.

| Field | Type | Description |
|-------|------|-------------|
| `client_ip` | string | Client IP (Sentinel masks last octet) |
| `user_agent` | string | Raw User-Agent header |
| `request_url` | string | Full request URL (Sentinel strips query params) |
| `request_method` | string | HTTP method (GET, POST, etc.) |
| `referer` | string | Referer header (Sentinel strips query params) |
| `device_type` | string | `desktop` / `mobile` / `tablet` / `bot` |
| `os` | string | Operating system name |
| `browser` | string | Browser name |
| `country` | string | Country code (if available from GeoIP) |
| `source_file` | string | Relative file path where error originated |
| `source_line` | integer | Line number |
| `source_function` | string | Function/method name |

## Notes

- This repo currently does NOT send `stack_hash` or `metadata` — that's fine, `request_context` is independent
- The HMAC auth in this repo doesn't include `app_id` in the derivation (unlike Claros/Recruitment) — no change needed there, this is a payload-only change
- The field is fully optional — if omitted, Sentinel still accepts the report, just without context data

## Testing

- Trigger a test error and verify the Sentinel payload includes `request_context`
- Verify `source_file` paths are relative (no `/opt/` or `/home/` prefixes)
- Verify the existing error reporting still works (backward compat)
