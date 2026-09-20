"""Academic tools — get_grades, get_homework, get_assignments."""

from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..errors import handle_errors
from ..filters import filter_timeline_events
from ..serializers import extract_assignment_fields, extract_homework_fields, lean_grade, lean_json
from ..session import SessionManager


def register(mcp: FastMCP, sessions: SessionManager) -> None:

    @mcp.tool()
    @handle_errors("get_grades")
    def get_grades(term: str = "", year: int = 0, school: str = "") -> str:
        """
        Get student grades/marks.

        Args:
            term: Term/semester filter (leave empty for all)
            year: School year filter (leave 0 for current)
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean grade records with percent, class_avg, etc.
        """
        kwargs: dict[str, Any] = {}
        if term:
            kwargs["term"] = term
        if year:
            kwargs["year"] = year

        def _fetch(edu):
            return [lean_grade(g) for g in edu.get_grades(**kwargs)]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_homework")
    def get_homework(since_days: int = 30, status: str = "", school: str = "") -> str:
        """
        Get homework assignments from the last N days.

        Args:
            since_days: How many days back to search (default 30)
            status: Filter by status — "active" (not done), "done", or "" (all, default)
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of homework items with title, subject, due_date, etc.
        """
        since = date.today() - timedelta(days=since_days)

        def _fetch(edu):
            events = edu.get_notification_history(since)
            events_filtered = filter_timeline_events(
                events,
                event_type="homework,etesthw",
                status=status,
                limit=200,
            )
            return [extract_homework_fields(e) for e in events_filtered]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_assignments")
    def get_assignments(since_days: int = 30, status: str = "", event_type: str = "", school: str = "") -> str:
        """
        Get all assignments (homework, tests, exams, projects, etc.).

        Args:
            since_days: How many days back to search (default 30)
            status: Filter by status — "active", "done", or "" (all, default)
            event_type: Narrow to specific types (comma-separated).
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of assignment items
        """
        since = date.today() - timedelta(days=since_days)
        types = event_type or "homework,etesthw,bexam,sexam,oexam,rexam,pexam,testing"

        def _fetch(edu):
            events = edu.get_notification_history(since)
            events_filtered = filter_timeline_events(
                events,
                event_type=types,
                status=status,
                limit=200,
            )
            return [extract_assignment_fields(e) for e in events_filtered]

        return lean_json(sessions.for_all(_fetch, school))
