"""Calendar tools — get_school_days (is-the-kid-at-school-over-lunch view).

Fuses the disruptions Edupage *does* expose — multi-day trips (Klassenfahrt),
single-day excursions (Ausflug / Wandertag), and the student's own absences —
into one per-date answer to "is the kid at school over lunch?".

HOLIDAYS ARE OUT OF SCOPE. Edupage notification history does not reliably carry
public- or state-level (Brandenburg) holiday closures, so this tool never
guesses school-closed-for-holiday. Dates with no detected disruption come back
``in_school=null`` (unknown), NOT True. The caller must cross-check a public
holiday source / the caterer's menu to be sure.
"""

import re
from datetime import date, datetime, timedelta

from mcp.server.fastmcp import FastMCP

from ..dates import extract_event_date
from ..errors import error
from ..filters import filter_timeline_events
from ..resolvers import resolve_student_across_sessions
from ..serializers import lean_json
from ..session import SessionManager

# Event types that mean "the class is physically away" for part or all of a day.
_TRIP_TYPES = {"trip", "schoolevent"}
_EXCURSION_TYPES = {"excursion", "culture"}
# Keyword fallbacks (titles are free text; types are not always set precisely).
_TRIP_KEYWORDS = ("klassenfahrt", "schulfahrt", "schullandheim", "fahrt")
_EXCURSION_KEYWORDS = ("ausflug", "wandertag", "exkursion", "excursion", "wandern")

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# An explicit date RANGE in a title: "DD.MM.[YYYY] - DD.MM.YYYY". The start year
# may be omitted ("10.6.-12.6.2026") and is then inherited from the end; the end
# year is REQUIRED so stray numerals are never taken as a range.
_RANGE_RE = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})?\s*[-–—]\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})"
)


def _norm_year(year_s: str) -> int:
    n = int(year_s)
    return n + 2000 if n < 100 else n


def _extract_date_range(event) -> tuple[date | None, date | None]:
    """Return (start, end) for an event. Single-date events get (d, d).

    Detects an explicit ``DD.MM.[YYYY] - DD.MM.YYYY`` range in the title (a
    year-less start inherits the end's year, fixing year-boundary drift), and
    otherwise falls back to the single parsed event date. Never raises.
    """
    text = getattr(event, "text", None) or ""
    ad = getattr(event, "additional_data", None)
    if isinstance(ad, dict):
        text = " ".join(
            str(ad.get(k) or "") for k in ("nazov", "title", "name")
        ) + " " + text

    m = _RANGE_RE.search(text)
    if m:
        end_year = _norm_year(m.group(6))
        try:
            d2 = date(end_year, int(m.group(5)), int(m.group(4)))
            if m.group(3):
                d1 = date(_norm_year(m.group(3)), int(m.group(2)), int(m.group(1)))
            else:
                # Start year omitted: assume the end's year, unless that puts the
                # start after the end (a year-crossing range like 28.12.–03.01.),
                # in which case the start belongs to the previous year.
                d1 = date(end_year, int(m.group(2)), int(m.group(1)))
                if d1 > d2:
                    d1 = date(end_year - 1, int(m.group(2)), int(m.group(1)))
            return (d1, d2) if d1 <= d2 else (d2, d1)
        except ValueError:
            pass

    single = extract_event_date(event)
    return single, single


def _classify(event) -> str | None:
    """Return 'trip' | 'excursion' | None for a disruption-relevant event."""
    et = getattr(event, "event_type", None)
    type_val = et.value if hasattr(et, "value") else str(et) if et else ""
    text = (getattr(event, "text", None) or "")
    ad = getattr(event, "additional_data", None)
    if isinstance(ad, dict):
        text += " " + " ".join(str(ad.get(k) or "") for k in ("nazov", "title", "name"))
    text_low = text.lower()

    if type_val in _TRIP_TYPES or any(k in text_low for k in _TRIP_KEYWORDS):
        return "trip"
    if type_val in _EXCURSION_TYPES or any(k in text_low for k in _EXCURSION_KEYWORDS):
        return "excursion"
    return None


def register(mcp: FastMCP, sessions: SessionManager) -> None:

    @mcp.tool()
    def get_school_days(
        student_name: str = "",
        from_date: str = "",
        to_date: str = "",
        school: str = "",
    ) -> str:
        """
        Per-date "is the kid at school over lunch?" view for a date range.

        Fuses three disruption sources Edupage *does* expose:
          - multi-day trips (Klassenfahrt) — date range parsed best-effort from
            the title (single date or DD.MM.YYYY–DD.MM.YYYY range);
          - single-day excursions (Ausflug / Wandertag / excursion event types);
          - the student's own absences (same path as get_absences).

        Each disruption sets in_school=False for the affected date(s). Dates with
        NO detected disruption are returned in_school=null (UNKNOWN) — never True.

        ⚠️  HOLIDAYS ARE NOT COVERED. Public / Brandenburg state holidays and
        school-closure days are not reliably present in Edupage data, so this
        tool does not detect them and will report in_school=null for such days.
        The caller MUST cross-check a public-holiday source or the caterer's menu
        before concluding a child is at school on a null day.

        Args:
            student_name: Student name (absences are student-specific). If empty,
                only trips/excursions are fused (no absences).
            from_date: Start date (YYYY-MM-DD). Defaults to today.
            to_date: End date (YYYY-MM-DD). Defaults to from_date + 14 days.
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of {date, weekday, in_school, reason, source} per date,
            ordered ascending. in_school is False (disrupted) or null (unknown).
        """
        try:
            start = (
                datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else date.today()
            )
        except ValueError:
            return error("get_school_days", f"Invalid from_date: {from_date!r} (use YYYY-MM-DD).")
        try:
            end = (
                datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else start + timedelta(days=14)
            )
        except ValueError:
            return error("get_school_days", f"Invalid to_date: {to_date!r} (use YYYY-MM-DD).")
        if end < start:
            return error("get_school_days", "to_date is before from_date.")

        # Resolve the student/session up front when a name is given (so absences
        # are student-specific and the right school is auto-detected).
        edu_for_student = None
        if student_name:
            edu_for_student, _student, err = resolve_student_across_sessions(
                sessions, student_name, school
            )
            if err:
                return error("get_school_days", err)

        # History must reach back far enough to catch a trip announced months
        # ago whose dates land inside the window.
        since = min(start, date.today()) - timedelta(days=180)

        def _collect(edu) -> dict[date, dict]:
            """Build {date: {source, reason}} of disruptions overlapping the window."""
            disruptions: dict[date, dict] = {}
            events = edu.get_notification_history(since)

            # Trips + excursions.
            event_items = filter_timeline_events(
                events,
                event_type="event,schoolevent,excursion,trip,culture",
                limit=1000,
            )
            for e in event_items:
                kind = _classify(e)
                if kind is None:
                    continue
                d_start, d_end = _extract_date_range(e)
                if d_start is None:
                    continue
                d_end = d_end or d_start
                title = (getattr(e, "text", None) or "").strip()
                ad = getattr(e, "additional_data", None)
                if isinstance(ad, dict):
                    title = (ad.get("nazov") or ad.get("title") or title or "").strip()
                cur = d_start
                while cur <= d_end:
                    if start <= cur <= end:
                        # Trips win over excursions if both land on a date.
                        existing = disruptions.get(cur)
                        if existing is None or (existing["source"] != "trip" and kind == "trip"):
                            disruptions[cur] = {
                                "source": kind,
                                "reason": title or kind.capitalize(),
                            }
                    cur += timedelta(days=1)

            # Absences (student-specific).
            if student_name:
                absence_items = filter_timeline_events(
                    events,
                    event_type="student_absent,ospravedlnenka",
                    limit=500,
                )
                for e in absence_items:
                    ts = getattr(e, "timestamp", None)
                    a_date = ts.date() if isinstance(ts, datetime) else ts
                    if a_date is None or not (start <= a_date <= end):
                        continue
                    # Absence is the strongest signal — it overrides.
                    disruptions[a_date] = {
                        "source": "absence",
                        "reason": (getattr(e, "text", None) or "Absent").strip(),
                    }
            return disruptions

        if student_name and edu_for_student is not None:
            disruptions = _collect(edu_for_student)
        else:
            # Merge across all sessions (or the one filtered by `school`).
            disruptions = {}
            all_sessions = sessions.get_all()
            if school:
                if school not in all_sessions:
                    available = ", ".join(all_sessions.keys())
                    return error("get_school_days", f"School '{school}' not found. Available: {available}")
                all_sessions = {school: all_sessions[school]}
            for _sub, edu in all_sessions.items():
                try:
                    for d, info in _collect(edu).items():
                        if d not in disruptions:
                            disruptions[d] = info
                except Exception:  # noqa: BLE001 — one school failing must not sink the rest
                    continue

        out = []
        cur = start
        while cur <= end:
            info = disruptions.get(cur)
            out.append({
                "date": cur.isoformat(),
                "weekday": _WEEKDAYS[cur.weekday()],
                # False when a disruption is known; null (unknown) otherwise.
                # Never True — holidays/closures are out of scope (see docstring).
                "in_school": False if info else None,
                "reason": info["reason"] if info else None,
                "source": info["source"] if info else None,
            })
            cur += timedelta(days=1)
        return lean_json(out)
