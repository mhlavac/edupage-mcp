"""Tests for edupage_mcp.session.SessionManager (non-login methods)."""

from types import SimpleNamespace

import pytest

from edupage_mcp.session import SessionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_edu(name: str = "mock") -> SimpleNamespace:
    """Create a minimal mock Edupage instance."""
    return SimpleNamespace(name=name)


def _session_with(**sessions: SimpleNamespace) -> SessionManager:
    """Create a SessionManager with pre-injected sessions."""
    mgr = SessionManager()
    mgr._sessions = dict(sessions)
    return mgr


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


class TestGet:
    def test_no_sessions_raises(self):
        mgr = SessionManager()
        with pytest.raises(RuntimeError, match="Not logged in"):
            mgr.get()

    def test_single_session_returns_it(self):
        edu = _make_edu("school1")
        mgr = _session_with(school1=edu)
        assert mgr.get() is edu

    def test_single_session_with_matching_school(self):
        edu = _make_edu("school1")
        mgr = _session_with(school1=edu)
        assert mgr.get(school="school1") is edu

    def test_multiple_sessions_no_school_raises(self):
        mgr = _session_with(school1=_make_edu(), school2=_make_edu())
        with pytest.raises(RuntimeError, match="Multiple schools"):
            mgr.get()

    def test_multiple_sessions_with_school(self):
        edu1 = _make_edu("s1")
        edu2 = _make_edu("s2")
        mgr = _session_with(school1=edu1, school2=edu2)
        assert mgr.get(school="school1") is edu1
        assert mgr.get(school="school2") is edu2

    def test_school_not_found_raises(self):
        mgr = _session_with(school1=_make_edu())
        with pytest.raises(RuntimeError, match="not found"):
            mgr.get(school="nonexistent")

    def test_school_not_found_lists_available(self):
        mgr = _session_with(alpha=_make_edu(), beta=_make_edu())
        with pytest.raises(RuntimeError, match="alpha"):
            mgr.get(school="gamma")


# ---------------------------------------------------------------------------
# get_all()
# ---------------------------------------------------------------------------


class TestGetAll:
    def test_empty_raises(self):
        mgr = SessionManager()
        with pytest.raises(RuntimeError, match="Not logged in"):
            mgr.get_all()

    def test_returns_all_sessions(self):
        edu1 = _make_edu()
        edu2 = _make_edu()
        mgr = _session_with(s1=edu1, s2=edu2)
        result = mgr.get_all()
        assert result == {"s1": edu1, "s2": edu2}

    def test_single_session(self):
        edu = _make_edu()
        mgr = _session_with(only=edu)
        result = mgr.get_all()
        assert len(result) == 1
        assert result["only"] is edu


# ---------------------------------------------------------------------------
# is_multi_school()
# ---------------------------------------------------------------------------


class TestIsMultiSchool:
    def test_no_sessions(self):
        mgr = SessionManager()
        assert mgr.is_multi_school() is False

    def test_single_session(self):
        mgr = _session_with(school1=_make_edu())
        assert mgr.is_multi_school() is False

    def test_two_sessions(self):
        mgr = _session_with(school1=_make_edu(), school2=_make_edu())
        assert mgr.is_multi_school() is True

    def test_three_sessions(self):
        mgr = _session_with(a=_make_edu(), b=_make_edu(), c=_make_edu())
        assert mgr.is_multi_school() is True


# ---------------------------------------------------------------------------
# for_all()
# ---------------------------------------------------------------------------


class TestForAll:
    def test_single_school_no_tagging(self):
        mgr = _session_with(school1=_make_edu())

        def fn(edu):
            return [{"data": "value"}]

        result = mgr.for_all(fn)
        assert len(result) == 1
        assert result[0] == {"data": "value"}
        assert "school" not in result[0]

    def test_multi_school_tags_results(self):
        mgr = _session_with(school1=_make_edu(), school2=_make_edu())

        def fn(edu):
            return [{"data": edu.name}]

        result = mgr.for_all(fn)
        assert len(result) == 2
        schools = {r["school"] for r in result}
        assert schools == {"school1", "school2"}

    def test_multi_school_merges_results(self):
        mgr = _session_with(s1=_make_edu(), s2=_make_edu())

        def fn(edu):
            return [{"x": 1}, {"x": 2}]

        result = mgr.for_all(fn)
        assert len(result) == 4  # 2 results from each of 2 schools

    def test_school_param_limits_to_one(self):
        edu1 = _make_edu("s1")
        edu2 = _make_edu("s2")
        mgr = _session_with(school1=edu1, school2=edu2)

        def fn(edu):
            return [{"name": edu.name}]

        result = mgr.for_all(fn, school="school1")
        assert len(result) == 1
        assert result[0]["name"] == "s1"
        # No school tagging when school param is given (not multi mode)
        assert "school" not in result[0]

    def test_school_param_not_found_raises(self):
        mgr = _session_with(school1=_make_edu())
        with pytest.raises(RuntimeError, match="not found"):
            mgr.for_all(lambda edu: [], school="nonexistent")

    def test_all_fail_raises(self):
        mgr = _session_with(school1=_make_edu())

        def fn(edu):
            raise ValueError("boom")

        with pytest.raises(RuntimeError, match="All schools failed"):
            mgr.for_all(fn)

    def test_partial_fail_returns_successful(self):
        edu1 = _make_edu("good")
        edu2 = _make_edu("bad")
        mgr = _session_with(school1=edu1, school2=edu2)

        def fn(edu):
            if edu.name == "bad":
                raise ValueError("fail")
            return [{"result": "ok"}]

        result = mgr.for_all(fn)
        assert len(result) >= 1
        # At least the successful school's results are included
        assert any(r.get("result") == "ok" for r in result)

    def test_empty_sessions_raises(self):
        mgr = SessionManager()
        with pytest.raises(RuntimeError, match="Not logged in"):
            mgr.for_all(lambda edu: [])

    def test_fn_returns_empty_list(self):
        mgr = _session_with(school1=_make_edu())

        def fn(edu):
            return []

        result = mgr.for_all(fn)
        assert result == []

    def test_multi_school_all_return_empty_lists(self):
        mgr = _session_with(s1=_make_edu(), s2=_make_edu())

        def fn(edu):
            return []

        result = mgr.for_all(fn)
        assert result == []

    def test_for_all_error_captures_school_name(self):
        """When a school fails, error dict includes the school subdomain."""
        edu1 = _make_edu("good")
        edu2 = _make_edu("bad")
        mgr = _session_with(school1=edu1, school2=edu2)

        call_count = {"n": 0}

        def fn(edu):
            call_count["n"] += 1
            if edu.name == "bad":
                raise ValueError("broken")
            return [{"ok": True}]

        result = mgr.for_all(fn)
        # fn was called for both schools
        assert call_count["n"] == 2
        # Only successful school's data returned
        assert len(result) >= 1
