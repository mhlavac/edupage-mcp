"""Timeline tools — get_timeline, get_notifications, get_notification_history."""

from datetime import date, datetime, timedelta

from mcp.server.fastmcp import FastMCP

from ..errors import handle_errors
from ..filters import filter_timeline_events
from ..serializers import lean_json, lean_timeline_event
from ..session import SessionManager


def register(mcp: FastMCP, sessions: SessionManager) -> None:

    @mcp.tool()
    @handle_errors("get_timeline")
    def get_timeline(
        status: str = "active",
        starred: str = "",
        event_type: str = "",
        category: str = "",
        date_from: str = "",
        date_to: str = "",
        by_event_date: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_system: bool = False,
        school: str = "",
    ) -> str:
        """
        Get the visible timeline (recent messages, assignments, grades).

        Args:
            status: Filter by status — "active" (default), "done", or "all".
            starred: Filter by starred — "yes", "no", or "" (all).
            event_type: Raw type filter (comma-separated, e.g. "sprava,znamka").
            category: Human-friendly category. One of: homework, grades, exams,
                      messages, absences, events, news.
            date_from: Start date (YYYY-MM-DD) for date range filter.
            date_to: End date (YYYY-MM-DD) for date range filter.
            by_event_date: When true, date_from/date_to filter on the parsed
                      *event date* (from the title, e.g. "... -  17.06.2026")
                      rather than the post timestamp. Default false.
            limit: Max items to return (default 50).
            offset: Items to skip for pagination.
            include_system: Include system events like H_* types (default false).
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean timeline events
        """
        def _fetch(edu):
            events = edu.get_notifications()
            events_filtered = filter_timeline_events(
                events,
                include_system=include_system,
                status="" if status == "all" else status,
                starred=starred,
                event_type=event_type,
                category=category,
                date_from=date_from,
                date_to=date_to,
                by_event_date=by_event_date,
                limit=limit,
                offset=offset,
            )
            return [lean_timeline_event(e) for e in events_filtered]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_notifications")
    def get_notifications(
        status: str = "",
        starred: str = "",
        event_type: str = "",
        category: str = "",
        date_from: str = "",
        date_to: str = "",
        by_event_date: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_system: bool = False,
        school: str = "",
    ) -> str:
        """
        Get recent notifications.

        Args:
            status: Filter — "active", "done", or "" (all, default).
            starred: Filter — "yes", "no", or "" (all).
            event_type: Raw type filter (comma-separated).
            category: Category filter: homework, grades, exams, messages, absences, events, news.
            date_from: Start date (YYYY-MM-DD) for date range filter.
            date_to: End date (YYYY-MM-DD) for date range filter.
            by_event_date: When true, date_from/date_to filter on the parsed
                      *event date* (from the title) rather than the post
                      timestamp. Default false.
            limit: Max items (default 50).
            offset: Skip items for pagination.
            include_system: Include system events (default false).
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean notification events
        """
        def _fetch(edu):
            events = edu.get_notifications()
            events_filtered = filter_timeline_events(
                events,
                include_system=include_system,
                status=status,
                starred=starred,
                event_type=event_type,
                category=category,
                date_from=date_from,
                date_to=date_to,
                by_event_date=by_event_date,
                limit=limit,
                offset=offset,
            )
            return [lean_timeline_event(e) for e in events_filtered]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_notification_history")
    def get_notification_history(since_date: str = "", status: str = "", starred: str = "",
                                  event_type: str = "", category: str = "", limit: int = 50,
                                  offset: int = 0, include_system: bool = False, school: str = "") -> str:
        """
        Get notification history since a given date.

        Args:
            since_date: Start date in YYYY-MM-DD format. Defaults to 7 days ago.
            status: Filter — "active", "done", or "" (all, default).
            starred: Filter — "yes", "no", or "" (all).
            event_type: Raw type filter (comma-separated).
            category: Category filter: homework, grades, exams, messages, absences, events, news.
            limit: Max items (default 50).
            offset: Skip items for pagination.
            include_system: Include system events (default false).
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean notification events
        """
        dt = datetime.strptime(since_date, "%Y-%m-%d").date() if since_date else date.today() - timedelta(days=7)

        def _fetch(edu):
            events = edu.get_notification_history(dt)
            events_filtered = filter_timeline_events(
                events,
                include_system=include_system,
                status=status,
                starred=starred,
                event_type=event_type,
                category=category,
                limit=limit,
                offset=offset,
            )
            return [lean_timeline_event(e) for e in events_filtered]

        return lean_json(sessions.for_all(_fetch, school))
