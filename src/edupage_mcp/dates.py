"""Event-date extraction for Edupage timeline events.

Edupage "event" timeline items store the *post* date in ``timestamp`` — the
date the announcement was published — not the date the event actually takes
place. The real event date lives in the title/text, formatted like
``"Udalosť: <name> -  DD.MM.YYYY"`` (1–2 spaces before the date), or is
sometimes carried in a structured field of ``additional_data``.

``extract_event_date`` is a pure helper that recovers the real event date,
preferring a structured field when present and falling back to a regex over
the title/text. It never raises — unparseable input yields ``None``.
"""

import re
from datetime import date, datetime

# A dotted "DD.MM.YYYY" / "DD.MM.YY" date — the year is REQUIRED. Yearless
# "DD.MM." and chapter/task references like "Kapitel 1.2.3" or "Aufgabe 2.5."
# must NOT be mistaken for an event date (they'd otherwise be stamped onto every
# homework/message item). Real Edupage event titles always carry the full year.
# We scan for the *last* match so a leading "5K Lauf" numeral is not mistaken
# for the date.
_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")

# The one unambiguous, explicitly-named event-date attribute (highest priority).
_EVENT_DATE_ATTR = "event_date"
# Ambiguous structured attrs / additional_data keys — these often hold the
# *post* date rather than the event date, so they are consulted only as a LAST
# resort, after the title (the reliable source for Edupage events).
_FALLBACK_ATTRS = ("date", "start")
_ADDITIONAL_DATA_KEYS = ("date", "datum", "dateFrom", "datefrom", "event_date", "start")


def _coerce_to_date(value: object) -> date | None:
    """Best-effort coercion of an arbitrary value to a ``date``. Never raises."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Try ISO first (YYYY-MM-DD[ ...]) then dotted European forms.
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(text[: len(fmt) + 4], fmt).date()
            except ValueError:
                continue
        # Fall back to the regex scan below.
        return _parse_from_text(text)
    return None


def _parse_from_text(text: str | None) -> date | None:
    """Scan free text for a dotted ``DD.MM.YYYY`` / ``DD.MM.YY`` date (year required)."""
    if not text:
        return None
    matches = list(_DATE_RE.finditer(text))
    if not matches:
        return None
    # Prefer the last date-looking token (event titles put the date at the end).
    for m in reversed(matches):
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        except (TypeError, ValueError):
            continue
        if year < 100:  # two-digit year -> 2000s
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def extract_event_date(event: object) -> date | None:
    """Return the real event date for a timeline event, or ``None``.

    Resolution order — the title beats the post date:

    1. An explicit ``event_date`` attribute on the object, if coercible.
    2. A dotted date parsed from the event ``text`` / ``title`` — the reliable
       source for Edupage "event" items (``"… -  DD.MM.YYYY"``).
    3. A dotted date inside an ``additional_data`` title field
       (``nazov``/``title``/``name``).
    4. LAST resort: ambiguous structured fields (``date``/``start`` attrs or
       ``additional_data`` date keys), which frequently hold the *post* date.

    Pure and defensive — any missing/garbage field is skipped, never raised.
    """
    # 1. The one explicitly-named event-date attribute.
    coerced = _coerce_to_date(getattr(event, _EVENT_DATE_ATTR, None))
    if coerced is not None:
        return coerced

    ad = getattr(event, "additional_data", None)

    # 2. Dotted date in the title / text (reliable for Edupage events).
    for attr in ("text", "title"):
        parsed = _parse_from_text(getattr(event, attr, None))
        if parsed is not None:
            return parsed

    # 3. Title carried inside additional_data.
    if isinstance(ad, dict):
        for key in ("nazov", "title", "name"):
            parsed = _parse_from_text(ad.get(key))
            if parsed is not None:
                return parsed

    # 4. Last resort: ambiguous structured fields (may be the POST date, so they
    #    rank below the title — see the precedence bug this guards against).
    for attr in _FALLBACK_ATTRS:
        coerced = _coerce_to_date(getattr(event, attr, None))
        if coerced is not None:
            return coerced
    if isinstance(ad, dict):
        for key in _ADDITIONAL_DATA_KEYS:
            coerced = _coerce_to_date(ad.get(key))
            if coerced is not None:
                return coerced

    return None
