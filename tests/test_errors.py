"""Tests for edupage_mcp.errors module."""

import json

from edupage_mcp.errors import _ERROR_HINTS, error, handle_errors

# ---------------------------------------------------------------------------
# error() function
# ---------------------------------------------------------------------------


class TestError:
    def test_returns_valid_json(self):
        result = error("login", "something went wrong")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_has_error_true(self):
        parsed = json.loads(error("login", "bad credentials"))
        assert parsed["error"] is True

    def test_has_action_field(self):
        parsed = json.loads(error("get_timetable", "not logged in"))
        assert parsed["action"] == "get_timetable"

    def test_has_detail_field(self):
        parsed = json.loads(error("login", "wrong password"))
        assert parsed["detail"] == "wrong password"

    def test_no_hint_when_not_provided(self):
        parsed = json.loads(error("login", "fail"))
        assert "hint" not in parsed

    def test_empty_hint_is_excluded(self):
        parsed = json.loads(error("login", "fail", hint=""))
        assert "hint" not in parsed

    def test_hint_included_when_provided(self):
        parsed = json.loads(error("login", "fail", hint="Try again"))
        assert parsed["hint"] == "Try again"

    def test_unicode_in_detail(self):
        parsed = json.loads(error("login", "prihlasenie zlyhalo"))
        assert parsed["detail"] == "prihlasenie zlyhalo"

    def test_unicode_in_hint(self):
        parsed = json.loads(error("login", "fail", hint="Skontrolujte heslo"))
        assert parsed["hint"] == "Skontrolujte heslo"


# ---------------------------------------------------------------------------
# handle_errors() decorator
# ---------------------------------------------------------------------------


class TestHandleErrors:
    def test_successful_function_returns_normally(self):
        @handle_errors("test_action")
        def success():
            return "ok"

        assert success() == "ok"

    def test_catches_exception_returns_json(self):
        @handle_errors("test_action")
        def fail():
            raise ValueError("boom")

        result = fail()
        parsed = json.loads(result)
        assert parsed["error"] is True
        assert parsed["action"] == "test_action"
        assert "boom" in parsed["detail"]

    def test_preserves_function_name(self):
        @handle_errors("test_action")
        def my_func():
            pass

        assert my_func.__name__ == "my_func"

    def test_passes_args_through(self):
        @handle_errors("test_action")
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_passes_kwargs_through(self):
        @handle_errors("test_action")
        def greet(name="world"):
            return f"hello {name}"

        assert greet(name="alice") == "hello alice"

    def test_error_hints_applied_for_known_exception(self):
        """When a known exception type is raised, the hint from _ERROR_HINTS should appear."""

        class BadCredentialsException(Exception):
            pass

        @handle_errors("login")
        def fail_login():
            raise BadCredentialsException("invalid")

        result = fail_login()
        parsed = json.loads(result)
        assert parsed["error"] is True
        assert parsed["hint"] == _ERROR_HINTS["BadCredentialsException"]

    def test_error_hints_applied_for_runtime_error(self):
        @handle_errors("something")
        def fail():
            raise RuntimeError("session expired")

        parsed = json.loads(fail())
        assert parsed["hint"] == _ERROR_HINTS["RuntimeError"]

    def test_no_hint_for_unknown_exception(self):
        @handle_errors("action")
        def fail():
            raise TypeError("unexpected")

        parsed = json.loads(fail())
        assert "hint" not in parsed or parsed.get("hint") == ""

    def test_error_hints_for_not_logged_in(self):
        class NotLoggedInException(Exception):
            pass

        @handle_errors("get_grades")
        def fail():
            raise NotLoggedInException("please login")

        parsed = json.loads(fail())
        assert "hint" in parsed
        assert "login" in parsed["hint"].lower()


# ---------------------------------------------------------------------------
# _ERROR_HINTS mapping
# ---------------------------------------------------------------------------


class TestErrorHints:
    def test_bad_credentials_key_exists(self):
        assert "BadCredentialsException" in _ERROR_HINTS

    def test_captcha_key_exists(self):
        assert "CaptchaException" in _ERROR_HINTS

    def test_not_logged_in_key_exists(self):
        assert "NotLoggedInException" in _ERROR_HINTS

    def test_runtime_error_key_exists(self):
        assert "RuntimeError" in _ERROR_HINTS

    def test_connection_error_key_exists(self):
        assert "ConnectionError" in _ERROR_HINTS

    def test_timeout_error_key_exists(self):
        assert "TimeoutError" in _ERROR_HINTS

    def test_all_hints_are_nonempty_strings(self):
        for key, hint in _ERROR_HINTS.items():
            assert isinstance(hint, str), f"Hint for {key} is not a string"
            assert len(hint) > 0, f"Hint for {key} is empty"
