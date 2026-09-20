"""Tests for the get_upcoming_events fix and the get_school_days tool.

These exercise the registered tool callables directly (no FastMCP transport,
no real Edupage API). A fake Edupage instance backs a single-school
SessionManager and returns synthetic SimpleNamespace timeline events.
"""

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from mcp.server.fastmcp import FastMCP

from edupage_mcp.session import SessionManager
from edupage_mcp.tools import calendar as calendar_tools
from edupage_mcp.tools import events as events_tools


class _MockEventType:
    def __init__(self, val):
        self.value = val


def _event(event_type, text, timestamp, additional_data=None):
    return SimpleNamespace(
        event_id=hash(text) & 0xFFFF,
        event_type=_MockEventType(event_type),
        timestamp=timestamp,
        text=text,
        author="Schule",
        additional_data=additional_data or {},
        is_done=False,
        is_starred=False,
        is_removed=False,
    )


class _FakeEdu:
    """Minimal Edupage stand-in: returns canned events / students."""

    def __init__(self, events, students=None):
        self._events = events
        self._students = students or []

    def get_notification_history(self, _since):
        return list(self._events)

    def get_students(self):
        return list(self._students)


def _single_school_sessions(edu):
    sm = SessionManager()
    sm._sessions = {"musterschule": edu}
    return sm


def _register_tool(register_fn, sessions):
    """Register a tool module and return {name: callable} of its tools."""
    mcp = FastMCP("test")
    register_fn(mcp, sessions)
    return {name: t.fn for name, t in mcp._tool_manager._tools.items()}


# ---------------------------------------------------------------------------
# get_upcoming_events — the core fix
# ---------------------------------------------------------------------------


class TestGetUpcomingEvents:
    def _today(self):
        return date.today()

    def test_future_event_posted_long_ago_surfaces(self):
        today = self._today()
        in_window = today + timedelta(days=10)
        # Posted 90 days ago, but the event date (in the title) is 10 days out.
        title = f"Udalosť: Sternwarte -  {in_window.strftime('%d.%m.%Y')}"
        posted_long_ago = datetime.combine(today - timedelta(days=90), datetime.min.time())
        edu = _FakeEdu([_event("event", title, posted_long_ago)])

        tools = _register_tool(events_tools.register, _single_school_sessions(edu))
        result = json.loads(tools["get_upcoming_events"](days_ahead=30))

        assert len(result) == 1
        assert result[0]["event_date"] == in_window.isoformat()

    def test_old_event_dropped(self):
        today = self._today()
        past = today - timedelta(days=5)
        title = f"Udalosť: Vergangenes Fest -  {past.strftime('%d.%m.%Y')}"
        posted = datetime.combine(today - timedelta(days=20), datetime.min.time())
        edu = _FakeEdu([_event("event", title, posted)])

        tools = _register_tool(events_tools.register, _single_school_sessions(edu))
        result = json.loads(tools["get_upcoming_events"](days_ahead=30))
        assert result == []

    def test_results_sorted_ascending_by_event_date(self):
        today = self._today()
        d_far = today + timedelta(days=20)
        d_near = today + timedelta(days=3)
        posted = datetime.combine(today - timedelta(days=60), datetime.min.time())
        edu = _FakeEdu([
            _event("event", f"Udalosť: Spaeter -  {d_far.strftime('%d.%m.%Y')}", posted),
            _event("event", f"Udalosť: Frueher -  {d_near.strftime('%d.%m.%Y')}", posted),
        ])

        tools = _register_tool(events_tools.register, _single_school_sessions(edu))
        result = json.loads(tools["get_upcoming_events"](days_ahead=30))
        dates = [r["event_date"] for r in result]
        assert dates == [d_near.isoformat(), d_far.isoformat()]

    def test_unparseable_event_falls_back_to_timestamp(self):
        today = self._today()
        ts = datetime.combine(today + timedelta(days=5), datetime.min.time())
        edu = _FakeEdu([_event("event", "Udalosť: Ohne Datum", ts)])

        tools = _register_tool(events_tools.register, _single_school_sessions(edu))
        result = json.loads(tools["get_upcoming_events"](days_ahead=30))
        assert len(result) == 1
        assert result[0]["event_date"] == (today + timedelta(days=5)).isoformat()


# ---------------------------------------------------------------------------
# get_school_days — trip / excursion / absence fusion
# ---------------------------------------------------------------------------


class TestGetSchoolDays:
    def test_fuses_trip_excursion_absence(self):
        # Window: a fixed 7-day range so dates are deterministic.
        start = date(2026, 6, 8)   # Monday
        end = date(2026, 6, 14)
        posted = datetime(2026, 1, 5, 9, 0)

        # Multi-day Klassenfahrt: 10.06–12.06.
        trip = _event(
            "trip",
            "Klassenfahrt Schullandheim -  10.06.2026 - 12.06.2026",
            posted,
        )
        # Single-day excursion: 09.06.
        excursion = _event("excursion", "Ausflug Zoo -  09.06.2026", posted)
        # Absence on 08.06 (timestamp-dated).
        absence = _event(
            "student_absent",
            "Krank gemeldet",
            datetime(2026, 6, 8, 7, 30),
        )
        student = SimpleNamespace(name="Max Mustermann", class_id=1)
        edu = _FakeEdu([trip, excursion, absence], students=[student])

        tools = _register_tool(calendar_tools.register, _single_school_sessions(edu))
        result = json.loads(
            tools["get_school_days"](
                student_name="Max Mustermann",
                from_date=start.isoformat(),
                to_date=end.isoformat(),
            )
        )

        by_date = {r["date"]: r for r in result}
        # 7 days returned.
        assert len(result) == 7

        assert by_date["2026-06-08"]["source"] == "absence"
        assert by_date["2026-06-08"]["in_school"] is False

        assert by_date["2026-06-09"]["source"] == "excursion"
        assert by_date["2026-06-09"]["in_school"] is False

        for d in ("2026-06-10", "2026-06-11", "2026-06-12"):
            assert by_date[d]["source"] == "trip"
            assert by_date[d]["in_school"] is False

        # Undisrupted days are UNKNOWN (null), never True (holidays out of scope).
        assert by_date["2026-06-13"]["in_school"] is None
        assert by_date["2026-06-13"]["source"] is None
        assert by_date["2026-06-14"]["in_school"] is None

    def test_no_disruptions_all_unknown(self):
        start = date(2026, 6, 8)
        end = date(2026, 6, 10)
        student = SimpleNamespace(name="Erika Beispiel", class_id=1)
        edu = _FakeEdu([], students=[student])

        tools = _register_tool(calendar_tools.register, _single_school_sessions(edu))
        result = json.loads(
            tools["get_school_days"](
                student_name="Erika Beispiel",
                from_date=start.isoformat(),
                to_date=end.isoformat(),
            )
        )
        assert len(result) == 3
        assert all(r["in_school"] is None for r in result)
        assert all(r["source"] is None for r in result)

    def test_weekday_labels(self):
        edu = _FakeEdu([], students=[SimpleNamespace(name="Max Mustermann", class_id=1)])
        tools = _register_tool(calendar_tools.register, _single_school_sessions(edu))
        result = json.loads(
            tools["get_school_days"](
                student_name="Max Mustermann",
                from_date="2026-06-08",  # Monday
                to_date="2026-06-08",
            )
        )
        assert result[0]["weekday"] == "Mon"

    def test_invalid_to_before_from(self):
        edu = _FakeEdu([], students=[SimpleNamespace(name="Max Mustermann", class_id=1)])
        tools = _register_tool(calendar_tools.register, _single_school_sessions(edu))
        result = json.loads(
            tools["get_school_days"](
                student_name="Max Mustermann",
                from_date="2026-06-10",
                to_date="2026-06-08",
            )
        )
        assert result.get("error") is True


class TestExtractDateRange:
    def test_full_range_both_years(self):
        e = _event("event", "Klassenfahrt -  10.06.2026 - 12.06.2026", datetime(2026, 1, 1))
        assert calendar_tools._extract_date_range(e) == (date(2026, 6, 10), date(2026, 6, 12))

    def test_yearless_start_inherits_end_year(self):
        e = _event("event", "Klassenfahrt 10.6.-12.6.2026", datetime(2026, 1, 1))
        assert calendar_tools._extract_date_range(e) == (date(2026, 6, 10), date(2026, 6, 12))

    def test_year_crossing_range_start_in_prior_year(self):
        # 28.12.–03.01.2027: the year-less start belongs to 2026, not 2027 —
        # must NOT yield a ~360-day span.
        e = _event("event", "Skifahrt 28.12.-03.01.2027", datetime(2026, 1, 1))
        assert calendar_tools._extract_date_range(e) == (date(2026, 12, 28), date(2027, 1, 3))

    def test_single_date_event(self):
        e = _event("excursion", "Ausflug Zoo -  09.06.2026", datetime(2026, 1, 1))
        assert calendar_tools._extract_date_range(e) == (date(2026, 6, 9), date(2026, 6, 9))

    def test_no_date_returns_none_pair(self):
        e = _event("event", "Elternabend kommende Woche", datetime(2026, 1, 1))
        assert calendar_tools._extract_date_range(e) == (None, None)
