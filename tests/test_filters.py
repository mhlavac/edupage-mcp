"""Tests for edupage_mcp.filters module."""

from datetime import datetime
from types import SimpleNamespace

from edupage_mcp.filters import (
    _EVENT_CATEGORIES,
    _SYSTEM_EVENT_TYPES,
    filter_timeline_events,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockEventType:
    """Mimics an enum-like event_type with a .value attribute."""

    def __init__(self, val: str):
        self.value = val


def _make_event(
    event_type: str = "sprava",
    timestamp: datetime | None = None,
    is_done: bool = False,
    is_starred: bool = False,
    is_removed: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        event_type=_MockEventType(event_type),
        timestamp=timestamp or datetime(2025, 6, 15, 10, 0),
        is_done=is_done,
        is_starred=is_starred,
        is_removed=is_removed,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_system_event_types_is_set(self):
        assert isinstance(_SYSTEM_EVENT_TYPES, set)

    def test_system_event_types_nonempty(self):
        assert len(_SYSTEM_EVENT_TYPES) > 0

    def test_known_system_event_present(self):
        assert "h_attendance" in _SYSTEM_EVENT_TYPES
        assert "h_timetable" in _SYSTEM_EVENT_TYPES
        assert "pipnutie" in _SYSTEM_EVENT_TYPES

    def test_event_categories_is_dict(self):
        assert isinstance(_EVENT_CATEGORIES, dict)

    def test_event_categories_nonempty(self):
        assert len(_EVENT_CATEGORIES) > 0

    def test_known_categories_present(self):
        assert "homework" in _EVENT_CATEGORIES
        assert "grades" in _EVENT_CATEGORIES
        assert "exams" in _EVENT_CATEGORIES
        assert "messages" in _EVENT_CATEGORIES
        assert "absences" in _EVENT_CATEGORIES
        assert "events" in _EVENT_CATEGORIES
        assert "news" in _EVENT_CATEGORIES

    def test_category_values_are_lists(self):
        for cat, types in _EVENT_CATEGORIES.items():
            assert isinstance(types, list), f"Category {cat} is not a list"
            assert len(types) > 0, f"Category {cat} is empty"


# ---------------------------------------------------------------------------
# System event filtering
# ---------------------------------------------------------------------------


class TestSystemEventFiltering:
    def test_system_events_hidden_by_default(self):
        events = [
            _make_event("sprava"),
            _make_event("h_attendance"),
            _make_event("h_timetable"),
        ]
        result = filter_timeline_events(events)
        types = [e.event_type.value for e in result]
        assert "sprava" in types
        assert "h_attendance" not in types
        assert "h_timetable" not in types

    def test_system_events_shown_with_include_system(self):
        events = [
            _make_event("sprava"),
            _make_event("h_attendance"),
        ]
        result = filter_timeline_events(events, include_system=True)
        types = [e.event_type.value for e in result]
        assert "sprava" in types
        assert "h_attendance" in types

    def test_all_system_types_filtered(self):
        """Each system event type should be filtered by default."""
        for sys_type in _SYSTEM_EVENT_TYPES:
            events = [_make_event(sys_type)]
            result = filter_timeline_events(events)
            assert len(result) == 0, f"System event {sys_type} was not filtered"


# ---------------------------------------------------------------------------
# Removed events
# ---------------------------------------------------------------------------


class TestRemovedEvents:
    def test_removed_events_excluded(self):
        events = [
            _make_event("sprava"),
            _make_event("sprava", is_removed=True),
        ]
        result = filter_timeline_events(events)
        assert len(result) == 1

    def test_removed_excluded_even_with_include_system(self):
        events = [_make_event("h_attendance", is_removed=True)]
        result = filter_timeline_events(events, include_system=True)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Status filter
# ---------------------------------------------------------------------------


class TestStatusFilter:
    def test_active_filter(self):
        events = [
            _make_event(is_done=False),
            _make_event(is_done=True),
        ]
        result = filter_timeline_events(events, status="active")
        assert all(not e.is_done for e in result)
        assert len(result) == 1

    def test_done_filter(self):
        events = [
            _make_event(is_done=False),
            _make_event(is_done=True),
        ]
        result = filter_timeline_events(events, status="done")
        assert all(e.is_done for e in result)
        assert len(result) == 1

    def test_empty_status_returns_all(self):
        events = [
            _make_event(is_done=False),
            _make_event(is_done=True),
        ]
        result = filter_timeline_events(events, status="")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Starred filter
# ---------------------------------------------------------------------------


class TestStarredFilter:
    def test_starred_yes(self):
        events = [
            _make_event(is_starred=True),
            _make_event(is_starred=False),
        ]
        result = filter_timeline_events(events, starred="yes")
        assert all(e.is_starred for e in result)
        assert len(result) == 1

    def test_starred_no(self):
        events = [
            _make_event(is_starred=True),
            _make_event(is_starred=False),
        ]
        result = filter_timeline_events(events, starred="no")
        assert all(not e.is_starred for e in result)
        assert len(result) == 1

    def test_starred_empty_returns_all(self):
        events = [
            _make_event(is_starred=True),
            _make_event(is_starred=False),
        ]
        result = filter_timeline_events(events, starred="")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Event type filter
# ---------------------------------------------------------------------------


class TestEventTypeFilter:
    def test_single_type(self):
        events = [
            _make_event("sprava"),
            _make_event("homework"),
            _make_event("znamka"),
        ]
        result = filter_timeline_events(events, event_type="homework")
        assert len(result) == 1
        assert result[0].event_type.value == "homework"

    def test_multiple_types_comma_separated(self):
        events = [
            _make_event("sprava"),
            _make_event("homework"),
            _make_event("znamka"),
        ]
        result = filter_timeline_events(events, event_type="homework,znamka")
        types = {e.event_type.value for e in result}
        assert types == {"homework", "znamka"}

    def test_type_with_spaces(self):
        events = [_make_event("homework")]
        result = filter_timeline_events(events, event_type=" homework ")
        assert len(result) == 1

    def test_no_match(self):
        events = [_make_event("sprava")]
        result = filter_timeline_events(events, event_type="homework")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Category filter
# ---------------------------------------------------------------------------


class TestCategoryFilter:
    def test_homework_category(self):
        events = [
            _make_event("homework"),
            _make_event("etesthw"),
            _make_event("sprava"),
        ]
        result = filter_timeline_events(events, category="homework")
        types = {e.event_type.value for e in result}
        assert types == {"homework", "etesthw"}

    def test_grades_category(self):
        events = [
            _make_event("znamka"),
            _make_event("znamkydoc"),
            _make_event("sprava"),
        ]
        result = filter_timeline_events(events, category="grades")
        types = {e.event_type.value for e in result}
        assert types == {"znamka", "znamkydoc"}

    def test_unknown_category_returns_all(self):
        """Unknown category is not in _EVENT_CATEGORIES so type_filter stays None."""
        events = [_make_event("sprava"), _make_event("homework")]
        result = filter_timeline_events(events, category="nonexistent")
        assert len(result) == 2

    def test_category_takes_priority_over_event_type(self):
        """When both category and event_type are given, category wins."""
        events = [_make_event("homework"), _make_event("sprava")]
        result = filter_timeline_events(events, category="homework", event_type="sprava")
        # Category 'homework' expands to {"homework", "etesthw"}, so only homework matches
        assert len(result) == 1
        assert result[0].event_type.value == "homework"


# ---------------------------------------------------------------------------
# Date range filter
# ---------------------------------------------------------------------------


class TestDateRangeFilter:
    def test_date_from(self):
        events = [
            _make_event(timestamp=datetime(2025, 6, 10)),
            _make_event(timestamp=datetime(2025, 6, 20)),
        ]
        result = filter_timeline_events(events, date_from="2025-06-15")
        assert len(result) == 1
        assert result[0].timestamp == datetime(2025, 6, 20)

    def test_date_to(self):
        events = [
            _make_event(timestamp=datetime(2025, 6, 10)),
            _make_event(timestamp=datetime(2025, 6, 20)),
        ]
        result = filter_timeline_events(events, date_to="2025-06-15")
        assert len(result) == 1
        assert result[0].timestamp == datetime(2025, 6, 10)

    def test_date_range_both(self):
        events = [
            _make_event(timestamp=datetime(2025, 6, 1)),
            _make_event(timestamp=datetime(2025, 6, 10)),
            _make_event(timestamp=datetime(2025, 6, 20)),
        ]
        result = filter_timeline_events(events, date_from="2025-06-05", date_to="2025-06-15")
        assert len(result) == 1
        assert result[0].timestamp == datetime(2025, 6, 10)

    def test_date_inclusive_boundaries(self):
        events = [
            _make_event(timestamp=datetime(2025, 6, 15, 8, 0)),
        ]
        result = filter_timeline_events(events, date_from="2025-06-15", date_to="2025-06-15")
        assert len(result) == 1

    def test_no_date_filter_returns_all(self):
        events = [
            _make_event(timestamp=datetime(2025, 1, 1)),
            _make_event(timestamp=datetime(2025, 12, 31)),
        ]
        result = filter_timeline_events(events)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Pagination (limit / offset)
# ---------------------------------------------------------------------------


class TestPagination:
    def test_default_limit_50(self):
        events = [_make_event(timestamp=datetime(2025, 6, 15, 0, i)) for i in range(60)]
        result = filter_timeline_events(events)
        assert len(result) == 50

    def test_custom_limit(self):
        events = [_make_event(timestamp=datetime(2025, 6, 15, 0, i)) for i in range(10)]
        result = filter_timeline_events(events, limit=3)
        assert len(result) == 3

    def test_offset(self):
        events = [_make_event(timestamp=datetime(2025, 6, 15, 0, i)) for i in range(10)]
        full = filter_timeline_events(events, limit=100)
        page2 = filter_timeline_events(events, limit=3, offset=3)
        assert len(page2) == 3
        assert page2[0].timestamp == full[3].timestamp

    def test_offset_beyond_end(self):
        events = [_make_event()]
        result = filter_timeline_events(events, offset=100)
        assert len(result) == 0

    def test_limit_zero_returns_empty(self):
        events = [_make_event()]
        result = filter_timeline_events(events, limit=0)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Sort order (newest first)
# ---------------------------------------------------------------------------


class TestSortOrder:
    def test_sorted_newest_first(self):
        events = [
            _make_event(timestamp=datetime(2025, 6, 10)),
            _make_event(timestamp=datetime(2025, 6, 20)),
            _make_event(timestamp=datetime(2025, 6, 15)),
        ]
        result = filter_timeline_events(events, limit=100)
        timestamps = [e.timestamp for e in result]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_already_sorted_stays_sorted(self):
        events = [
            _make_event(timestamp=datetime(2025, 6, 20)),
            _make_event(timestamp=datetime(2025, 6, 15)),
            _make_event(timestamp=datetime(2025, 6, 10)),
        ]
        result = filter_timeline_events(events, limit=100)
        timestamps = [e.timestamp for e in result]
        assert timestamps == [
            datetime(2025, 6, 20),
            datetime(2025, 6, 15),
            datetime(2025, 6, 10),
        ]


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------


class TestByEventDate:
    """Filtering on the parsed event date (from the title) vs. the timestamp."""

    def _evt(self, title, timestamp):
        return SimpleNamespace(
            event_type=_MockEventType("event"),
            timestamp=timestamp,
            text=title,
            additional_data={},
            is_done=False,
            is_starred=False,
            is_removed=False,
        )

    def test_default_filters_on_timestamp(self):
        # Posted (timestamp) Jan; event date in title is June. Default behavior
        # filters on the timestamp, so a June-range filter drops it.
        e = self._evt("Udalosť: Sommerfest -  15.06.2026", datetime(2026, 1, 10, 9, 0))
        result = filter_timeline_events([e], date_from="2026-06-01", date_to="2026-06-30")
        assert len(result) == 0

    def test_by_event_date_keeps_in_window_event(self):
        # Same event, but by_event_date filters on the June title date → kept.
        e = self._evt("Udalosť: Sommerfest -  15.06.2026", datetime(2026, 1, 10, 9, 0))
        result = filter_timeline_events(
            [e], date_from="2026-06-01", date_to="2026-06-30", by_event_date=True
        )
        assert len(result) == 1

    def test_by_event_date_excludes_out_of_window(self):
        e = self._evt("Udalosť: Herbstfest -  15.09.2026", datetime(2026, 1, 10, 9, 0))
        result = filter_timeline_events(
            [e], date_from="2026-06-01", date_to="2026-06-30", by_event_date=True
        )
        assert len(result) == 0

    def test_by_event_date_falls_back_to_timestamp_when_unparseable(self):
        # No date in title → falls back to timestamp, which is in window.
        e = self._evt("Udalosť: Versammlung", datetime(2026, 6, 10, 9, 0))
        result = filter_timeline_events(
            [e], date_from="2026-06-01", date_to="2026-06-30", by_event_date=True
        )
        assert len(result) == 1


class TestCombinedFilters:
    def test_status_and_type(self):
        events = [
            _make_event("homework", is_done=False),
            _make_event("homework", is_done=True),
            _make_event("sprava", is_done=False),
        ]
        result = filter_timeline_events(events, status="active", event_type="homework")
        assert len(result) == 1
        assert result[0].event_type.value == "homework"
        assert result[0].is_done is False

    def test_starred_and_date_range(self):
        events = [
            _make_event(timestamp=datetime(2025, 6, 10), is_starred=True),
            _make_event(timestamp=datetime(2025, 6, 20), is_starred=True),
            _make_event(timestamp=datetime(2025, 6, 15), is_starred=False),
        ]
        result = filter_timeline_events(events, starred="yes", date_from="2025-06-12")
        assert len(result) == 1
        assert result[0].is_starred is True

    def test_empty_event_list(self):
        assert filter_timeline_events([]) == []
