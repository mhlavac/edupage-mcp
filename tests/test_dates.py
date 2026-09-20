"""Tests for edupage_mcp.dates.extract_event_date."""

from datetime import date, datetime
from types import SimpleNamespace

from edupage_mcp.dates import extract_event_date


def _event(text="", title=None, additional_data=None, **kw):
    ns = SimpleNamespace(text=text, additional_data=additional_data or {}, **kw)
    if title is not None:
        ns.title = title
    return ns


# ---------------------------------------------------------------------------
# Regex fallback over the title / text
# ---------------------------------------------------------------------------


class TestTitleParsing:
    def test_udalost_full_date(self):
        e = _event("Udalosť: Sternwarte -  17.06.2026")
        assert extract_event_date(e) == date(2026, 6, 17)

    def test_udalost_numeral_name_not_mistaken(self):
        # "5K Lauf" leading numeral must NOT be parsed as the date.
        e = _event("Udalosť: 5K Lauf -  12.06.2026")
        assert extract_event_date(e) == date(2026, 6, 12)

    def test_termin_full_date(self):
        e = _event("Termin - 02.07.2026")
        assert extract_event_date(e) == date(2026, 7, 2)

    def test_no_date_returns_none(self):
        e = _event("Udalosť: Schulversammlung")
        assert extract_event_date(e) is None

    def test_two_digit_year(self):
        e = _event("Ausflug -  05.09.26")
        assert extract_event_date(e) == date(2026, 9, 5)

    def test_day_month_without_year_not_parsed(self):
        # Yearless "DD.MM." is intentionally NOT parsed — a real event title
        # carries the full year, and parsing yearless tokens would mis-read
        # chapter refs / task numbers (see the two tests below).
        e = _event("Wandertag - 14.05.")
        assert extract_event_date(e) is None

    def test_chapter_reference_not_a_date(self):
        # "Kapitel 1.2.3" must not be read as 01.02.<year>.
        e = _event("Lies Kapitel 1.2.3 bis Freitag")
        assert extract_event_date(e) is None

    def test_task_number_not_a_date(self):
        # "Aufgabe 2.5." (no year) must not be read as 02.05.<year>.
        e = _event("Aufgabe 2.5. erledigen")
        assert extract_event_date(e) is None

    def test_single_digit_day_and_month(self):
        e = _event("Event -  3.4.2026")
        assert extract_event_date(e) == date(2026, 4, 3)

    def test_invalid_date_returns_none(self):
        e = _event("Event -  45.99.2026")
        assert extract_event_date(e) is None

    def test_falls_back_to_title_attr(self):
        e = _event(text="", title="Konzert -  09.10.2026")
        assert extract_event_date(e) == date(2026, 10, 9)


# ---------------------------------------------------------------------------
# Structured fields take priority over the regex
# ---------------------------------------------------------------------------


class TestStructuredFields:
    def test_event_date_attr(self):
        e = _event("ignored text 01.01.2000", event_date=date(2026, 6, 17))
        assert extract_event_date(e) == date(2026, 6, 17)

    def test_event_date_datetime_attr(self):
        e = _event("", event_date=datetime(2026, 6, 17, 9, 30))
        assert extract_event_date(e) == date(2026, 6, 17)

    def test_date_attr_string_iso(self):
        e = _event("", date="2026-07-02")
        assert extract_event_date(e) == date(2026, 7, 2)

    def test_additional_data_date_key(self):
        # No title date present → additional_data['date'] is used as fallback.
        e = _event("", additional_data={"date": "2026-06-12"})
        assert extract_event_date(e) == date(2026, 6, 12)

    def test_title_date_beats_additional_data_post_date(self):
        # Regression: additional_data['date'] is the *post* date; the real event
        # date lives in the title and MUST win, or future events get dropped.
        e = _event(
            "Udalosť: Sternwarte -  17.06.2026",
            additional_data={"date": "2026-03-01"},
        )
        assert extract_event_date(e) == date(2026, 6, 17)

    def test_additional_data_dotted_date(self):
        e = _event("", additional_data={"datum": "17.06.2026"})
        assert extract_event_date(e) == date(2026, 6, 17)

    def test_additional_data_nazov_title(self):
        e = _event("", additional_data={"nazov": "Sternwarte -  17.06.2026"})
        assert extract_event_date(e) == date(2026, 6, 17)


# ---------------------------------------------------------------------------
# Defensiveness — never raises
# ---------------------------------------------------------------------------


class TestDefensive:
    def test_empty_object(self):
        assert extract_event_date(SimpleNamespace()) is None

    def test_none_text(self):
        assert extract_event_date(SimpleNamespace(text=None, additional_data=None)) is None

    def test_garbage_additional_data(self):
        e = SimpleNamespace(text="", additional_data="not-a-dict")
        assert extract_event_date(e) is None

    def test_empty_string(self):
        assert extract_event_date(_event("")) is None
