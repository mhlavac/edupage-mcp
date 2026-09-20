"""Session management — supports multiple Edupage instances (multi-school)."""

import logging
import os
from typing import Any, Callable

from .errors import error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import of edupage_api
# ---------------------------------------------------------------------------
_edupage_api = None


def _get_edupage_api():
    global _edupage_api
    if _edupage_api is None:
        try:
            import edupage_api as _mod
            _edupage_api = _mod
        except ImportError:
            raise RuntimeError(
                "edupage-api is not installed. Run: pip install edupage-api"
            )
    return _edupage_api


class SessionManager:
    """Manages one or more logged-in Edupage sessions (keyed by subdomain)."""

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}

    def get(self, school: str = "") -> Any:
        """Return a logged-in Edupage session.

        If school is specified, return that specific session.
        If only one session exists, return it.
        If multiple sessions exist and no school specified, raise with helpful message.
        """
        if not self._sessions:
            raise RuntimeError(
                "Not logged in. Call the 'login' tool (no arguments needed — "
                "credentials are read from environment variables)."
            )
        if school:
            if school not in self._sessions:
                available = ", ".join(self._sessions.keys())
                raise RuntimeError(f"School '{school}' not found. Available: {available}")
            return self._sessions[school]
        if len(self._sessions) == 1:
            return next(iter(self._sessions.values()))
        available = ", ".join(self._sessions.keys())
        raise RuntimeError(
            f"Multiple schools connected ({available}). "
            f"Specify the 'school' parameter."
        )

    def get_all(self) -> dict[str, Any]:
        """Return all logged-in sessions. Raises if none."""
        if not self._sessions:
            raise RuntimeError(
                "Not logged in. Call the 'login' tool (no arguments needed — "
                "credentials are read from environment variables)."
            )
        return self._sessions

    def is_multi_school(self) -> bool:
        """Return True if more than one school is connected."""
        return len(self._sessions) > 1

    def for_all(self, fn: Callable, school: str = "") -> list[dict]:
        """Run fn(edu) for each session, tag results with 'school' if multi, return merged list.

        fn takes an Edupage instance and returns list[dict].
        In multi-school mode, adds 'school' field to each result dict.
        If school param given, only run against that session.
        """
        sessions = self.get_all()
        if school:
            if school not in sessions:
                available = ", ".join(sessions.keys())
                raise RuntimeError(f"School '{school}' not found. Available: {available}")
            sessions = {school: sessions[school]}

        multi = self.is_multi_school() and not school
        merged: list[dict] = []
        errors: list[dict] = []
        for sub, edu in sessions.items():
            try:
                results = fn(edu)
                if multi:
                    for item in results:
                        item["school"] = sub
                merged.extend(results)
            except Exception as e:
                logger.warning("Error from %s: %s", sub, e)
                errors.append({"school": sub, "error": str(e)})

        if not merged and errors:
            raise RuntimeError(f"All schools failed: {errors}")
        return merged

    def login(self, username: str = "", password: str = "", subdomain: str = "") -> str:
        """Log in to Edupage. Returns status message."""
        username = username or os.environ.get("EDUPAGE_USERNAME", "")
        password = password or os.environ.get("EDUPAGE_PASSWORD", "")
        subdomain = subdomain or os.environ.get("EDUPAGE_SUBDOMAIN", "")

        if not username or not password or not subdomain:
            missing = [
                name
                for name, val in [
                    ("EDUPAGE_USERNAME", username),
                    ("EDUPAGE_PASSWORD", password),
                    ("EDUPAGE_SUBDOMAIN", subdomain),
                ]
                if not val
            ]
            return error(
                "login", f"Missing environment variable(s): {', '.join(missing)}",
                "Set them before starting the server.",
            )

        subdomains = [s.strip() for s in subdomain.split(",") if s.strip()]
        api = _get_edupage_api()
        successes = []
        failures = []

        for sub in subdomains:
            edu = api.Edupage()
            try:
                edu.login(username, password, sub)
                self._sessions[sub] = edu
                successes.append(sub)
            except api.exceptions.BadCredentialsException:
                failures.append(f"{sub}: wrong credentials")
            except api.exceptions.CaptchaException:
                failures.append(f"{sub}: CAPTCHA requested")
            except Exception as e:
                failures.append(f"{sub}: {e}")

        parts = []
        if successes:
            parts.append(f"Logged in: {', '.join(s + '.edupage.org' for s in successes)}")
        if failures:
            parts.append(f"Failed: {'; '.join(failures)}")

        if not successes:
            return error("login", "; ".join(failures))
        return ". ".join(parts)

    def login_auto(self, username: str = "", password: str = "") -> str:
        """Log in via the portal (auto-detect school). Returns status message."""
        username = username or os.environ.get("EDUPAGE_USERNAME", "")
        password = password or os.environ.get("EDUPAGE_PASSWORD", "")

        if not username or not password:
            missing = [
                name
                for name, val in [
                    ("EDUPAGE_USERNAME", username),
                    ("EDUPAGE_PASSWORD", password),
                ]
                if not val
            ]
            return error(
                "login_auto", f"Missing environment variable(s): {', '.join(missing)}",
                "Set them before starting the server.",
            )

        api = _get_edupage_api()
        edu = api.Edupage()
        try:
            edu.login_auto(username, password)
        except Exception as e:
            return error("login_auto", str(e))

        sub = getattr(edu, "subdomain", None) or "auto"
        self._sessions[sub] = edu
        return f"Logged in successfully via portal ({sub}.edupage.org)."

    def try_env_login(self) -> None:
        """Attempt to log in using environment variables at startup."""
        username = os.environ.get("EDUPAGE_USERNAME")
        password = os.environ.get("EDUPAGE_PASSWORD")
        subdomain = os.environ.get("EDUPAGE_SUBDOMAIN")

        if username and password and subdomain:
            subdomains = [s.strip() for s in subdomain.split(",") if s.strip()]
            api = _get_edupage_api()
            for sub in subdomains:
                edu = api.Edupage()
                try:
                    edu.login(username, password, sub)
                    self._sessions[sub] = edu
                    logger.info("Auto-logged in as %s on %s", username, sub)
                except Exception as e:
                    logger.warning("Auto-login failed for %s: %s", sub, e)
        elif username and password:
            api = _get_edupage_api()
            edu = api.Edupage()
            try:
                edu.login_auto(username, password)
                sub = getattr(edu, "subdomain", None) or "auto"
                self._sessions[sub] = edu
                logger.info("Auto-logged in as %s via portal (%s)", username, sub)
            except Exception as e:
                logger.warning("Auto-login via portal failed: %s", e)
