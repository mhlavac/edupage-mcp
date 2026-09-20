"""Event tools — get_absences, get_upcoming_events, get_student_summary."""

from datetime import date, datetime, timedelta

from mcp.server.fastmcp import FastMCP

from ..dates import extract_event_date
from ..errors import error, handle_errors
from ..filters import filter_timeline_events
from ..resolvers import resolve_class_for_student_across_sessions, resolve_student_across_sessions
from ..serializers import (
    additional_data,
    extract_homework_fields,
    lean_class,
    lean_grade,
    lean_json,
    lean_student,
    lean_timeline_event,
)
from ..session import SessionManager


def register(mcp: FastMCP, sessions: SessionManager) -> None:

    @mcp.tool()
    @handle_errors("get_absences")
    def get_absences(since_days: int = 30, student_name: str = "", school: str = "") -> str:
        """
        Get absence records from the last N days.

        Args:
            since_days: How many days back to search (default 30)
            student_name: Optional student name (searches all schools automatically).
            school: School subdomain (only needed with multiple schools and no student_name).

        Returns:
            JSON array of absence records with date, type, text, author
        """
        # If student_name given, auto-detect school
        if student_name:
            edu, _student, err = resolve_student_across_sessions(sessions, student_name, school)
            if err:
                return error("get_absences", err)
            since = date.today() - timedelta(days=since_days)
            events = edu.get_notification_history(since)
            events = filter_timeline_events(
                events,
                event_type="student_absent,ospravedlnenka",
                limit=200,
            )
            result = []
            for e in events:
                et = getattr(e, "event_type", None)
                type_val = et.value if hasattr(et, "value") else str(et) if et else ""
                author = getattr(e, "author", None)
                author_name = author.name if hasattr(author, "name") else str(author) if author else None
                result.append({
                    "date": e.timestamp.isoformat() if getattr(e, "timestamp", None) else None,
                    "type": "excused" if type_val == "ospravedlnenka" else "absent",
                    "text": getattr(e, "text", None),
                    "author": author_name,
                })
            return lean_json(result)

        # No student_name: merge from all sessions
        since = date.today() - timedelta(days=since_days)

        def _fetch(edu):
            events = edu.get_notification_history(since)
            events_filtered = filter_timeline_events(
                events,
                event_type="student_absent,ospravedlnenka",
                limit=200,
            )
            result = []
            for e in events_filtered:
                et = getattr(e, "event_type", None)
                type_val = et.value if hasattr(et, "value") else str(et) if et else ""
                author = getattr(e, "author", None)
                author_name = author.name if hasattr(author, "name") else str(author) if author else None
                result.append({
                    "date": e.timestamp.isoformat() if getattr(e, "timestamp", None) else None,
                    "type": "excused" if type_val == "ospravedlnenka" else "absent",
                    "text": getattr(e, "text", None),
                    "author": author_name,
                })
            return result

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_upcoming_events")
    def get_upcoming_events(days_ahead: int = 30, lookback_days: int = 180, school: str = "") -> str:
        """
        Get upcoming events and exams within the next N days.

        Edupage events store the *post* date (when the announcement was
        published) in their timestamp, while the real event date lives in the
        title (e.g. "Udalosť: Sternwarte -  17.06.2026"). An event can be
        announced months in advance, so this tool fetches notification history
        back ``lookback_days`` days, parses the real event date out of each
        item, and keeps those whose event date falls within
        [today, today + days_ahead]. Items whose date cannot be parsed fall
        back to their timestamp.

        Args:
            days_ahead: How many days ahead to look (default 30).
            lookback_days: How far back to fetch announcements, since events may
                have been posted long before they occur (default 180).
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of upcoming events sorted by event date (nearest first),
            each including the parsed ``event_date``.
        """
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)
        since = today - timedelta(days=lookback_days)

        event_types = (
            "event,schoolevent,excursion,trip,culture,parentsevening,meeting,bmeeting,"
            "bexam,sexam,oexam,rexam,pexam,testing"
        )

        def _fetch(edu):
            events = edu.get_notification_history(since)
            events_filtered = filter_timeline_events(
                events,
                event_type=event_types,
                limit=1000,
            )
            upcoming = []
            for e in events_filtered:
                ev_date = extract_event_date(e)
                if ev_date is None:
                    # Fall back to the post timestamp when the date is unparseable.
                    ts = getattr(e, "timestamp", None)
                    ev_date = ts.date() if isinstance(ts, datetime) else ts
                if ev_date is None or ev_date < today or ev_date > cutoff:
                    continue
                ad = additional_data(e)
                et = getattr(e, "event_type", None)
                type_val = et.value if hasattr(et, "value") else str(et) if et else None
                title = ad.get("nazov") or ad.get("title") or getattr(e, "text", "")
                ts = getattr(e, "timestamp", None)
                upcoming.append({
                    "event_id": getattr(e, "event_id", None),
                    "type": type_val,
                    "event_date": ev_date.isoformat(),
                    "posted_at": ts.isoformat() if ts else None,
                    "title": title,
                    "text": getattr(e, "text", None),
                    "is_done": getattr(e, "is_done", False),
                })
            return upcoming

        result = sessions.for_all(_fetch, school)
        result.sort(key=lambda x: x.get("event_date", ""))
        return lean_json(result)

    @mcp.tool()
    @handle_errors("get_student_summary")
    def get_student_summary(student_name: str = "", since_days: int = 14, school: str = "") -> str:
        """
        Get a comprehensive summary for a student: grades, homework, exams,
        absences, and messages — all in one call.

        Args:
            student_name: Student name (e.g. 'Jan Novak'). Use get_my_children() to find names.
            since_days: How many days back to include (default 14)
            school: School subdomain (only needed when student exists in multiple schools).

        Returns:
            JSON object with student, class, grades, homework, exams, absences, messages
        """
        student_info = None
        class_info = None

        if student_name:
            edu, student, cls, err = resolve_class_for_student_across_sessions(sessions, student_name, school)
            if err:
                return error("get_student_summary", err)
            student_info = lean_student(student)
            class_info = lean_class(cls) if cls else None
        else:
            edu = sessions.get(school)

        # Fetch notification history once
        since = date.today() - timedelta(days=since_days)
        events = edu.get_notification_history(since)

        # Partition by type
        homework_events = filter_timeline_events(events, event_type="homework,etesthw", limit=100)
        exam_events = filter_timeline_events(events, event_type="bexam,sexam,oexam,rexam,pexam,testing", limit=100)
        absence_events = filter_timeline_events(events, event_type="student_absent,ospravedlnenka", limit=100)
        message_events = filter_timeline_events(events, event_type="sprava", limit=50)

        # Fetch grades separately (richer data)
        try:
            grades = edu.get_grades()
            grade_list = []
            for g in grades:
                g_date = getattr(g, "date", None)
                if g_date:
                    g_date_val = g_date.date() if isinstance(g_date, datetime) else g_date
                    if g_date_val >= since:
                        grade_list.append(lean_grade(g))
                else:
                    grade_list.append(lean_grade(g))
        except Exception:
            grade_list = []

        summary = {
            "student": student_info,
            "class": class_info,
            "period": f"last {since_days} days (since {since.isoformat()})",
            "grades": grade_list,
            "homework": [extract_homework_fields(e) for e in homework_events],
            "exams": [lean_timeline_event(e) for e in exam_events],
            "absences": [
                {
                    "date": e.timestamp.isoformat() if getattr(e, "timestamp", None) else None,
                    "type": (
                        "excused" if (
                            getattr(e, "event_type", None)
                            and hasattr(e.event_type, "value")
                            and e.event_type.value == "ospravedlnenka"
                        ) else "absent"
                    ),
                    "text": getattr(e, "text", None),
                }
                for e in absence_events
            ],
            "messages": [lean_timeline_event(e) for e in message_events],
        }
        return lean_json(summary)
