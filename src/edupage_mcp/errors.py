"""Error handling utilities for Edupage MCP server."""

import functools
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_ERROR_HINTS: dict[str, str] = {
    "BadCredentialsException": "Wrong username or password. Check EDUPAGE_USERNAME and EDUPAGE_PASSWORD.",
    "CaptchaException": "Edupage is requesting a CAPTCHA. Log in via browser first, then retry.",
    "NotLoggedInException": "Not logged in. Call the 'login' tool first.",
    "RuntimeError": "Check that you are logged in (call 'login' tool).",
    "ConnectionError": "Network error. Check your internet connection.",
    "TimeoutError": "Request timed out. Edupage may be slow — try again.",
}


def error(action: str, detail: str, hint: str = "") -> str:
    """Return a structured JSON error string."""
    err: dict[str, Any] = {"error": True, "action": action, "detail": detail}
    if hint:
        err["hint"] = hint
    return json.dumps(err, ensure_ascii=False)


def handle_errors(action: str):
    """Decorator that catches exceptions and returns structured error JSON."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                exc_name = type(e).__name__
                hint = _ERROR_HINTS.get(exc_name, "")
                logger.exception("Error in %s: %s", action, e)
                return error(action, str(e), hint)
        return wrapper
    return decorator
