"""Timetable tools — get_timetable, get_next_week_timetable, get_timetable_changes."""

import logging
from datetime import date, datetime, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..errors import error, handle_errors
from ..resolvers import resolve_class_for_student_across_sessions
from ..serializers import lean_json, lean_timetable, serialize
from ..session import SessionManager

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, sessions: SessionManager) -> None:

    def _get_timetable_by_class(edu: Any, class_name: str, target_date: date) -> str:
        """Fetch timetable for a specific class by name."""
        classes = edu.get_classes()
        matched = [c for c in classes if c.name.lower() == class_name.lower()]
        if not matched:
            available = ", ".join(sorted(c.name for c in classes))
            return error("get_timetable", f"Class '{class_name}' not found.", f"Available classes: {available}")
        timetable = edu.get_timetable(matched[0], target_date)
        return lean_json(lean_timetable(timetable))

    @mcp.tool()
    @handle_errors("get_timetable")
    def get_timetable(date_str: str = "", class_name: str = "", student_name: str = "", school: str = "") -> str:
        """
        Get the timetable for a given date (defaults to today).

        Args:
            date_str: Date in YYYY-MM-DD format. Leave empty for today.
            class_name: Class name (e.g. '6e', '4a'). If empty, uses logged-in user's timetable.
            student_name: Student name to look up their class timetable (e.g. 'Jan Novak').
                          Resolves the student's class automatically (searches all schools).
            school: School subdomain (only needed with multiple schools and no student_name).

        Returns:
            JSON array of lean timetable lessons
        """
        target_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        )

        # Resolve student → class (auto-detects school)
        if student_name:
            edu, _student, cls, err = resolve_class_for_student_across_sessions(sessions, student_name, school)
            if err:
                return error("get_timetable", err)
            timetable = edu.get_timetable(cls, target_date)
            return lean_json(lean_timetable(timetable))

        edu = sessions.get(school)

        # If a class name is specified, look it up directly
        if class_name:
            return _get_timetable_by_class(edu, class_name, target_date)

        # Try the logged-in user's own timetable first
        try:
            timetable = edu.get_my_timetable(target_date)
            return lean_json(lean_timetable(timetable))
        except Exception:
            logger.debug("get_my_timetable failed, falling back to class lookup")

        # Fallback: get timetable via the class of the user's students
        try:
            students = edu.get_students()
            if students:
                classes = edu.get_classes()
                class_by_id: dict[int, Any] = {}
                for c in classes:
                    class_by_id[c.class_id] = c
                    class_by_id[abs(c.class_id)] = c
                for student in students:
                    class_id = getattr(student, "class_id", None)
                    if class_id and class_id in class_by_id:
                        try:
                            timetable = edu.get_timetable(class_by_id[class_id], target_date)
                            return lean_json(lean_timetable(timetable))
                        except Exception:
                            continue
        except Exception:
            pass

        return error(
            "get_timetable", "Could not fetch timetable.",
            "Try specifying student_name or class_name (e.g. '4a').",
        )

    @mcp.tool()
    @handle_errors("get_next_week_timetable")
    def get_next_week_timetable(class_name: str = "", student_name: str = "", school: str = "") -> str:
        """
        Get timetable for each day of the upcoming week (Mon-Fri).

        Args:
            class_name: Class name (e.g. '6e', '4a'). If empty, uses logged-in user's timetable.
            student_name: Student name to look up their class timetable (searches all schools).
            school: School subdomain (only needed with multiple schools and no student_name).

        Returns:
            JSON object keyed by date with lean timetable lessons
        """
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7 or 7
        monday = today + timedelta(days=days_until_monday)

        # Resolve target class (auto-detects school)
        target_class = None
        if student_name:
            edu, _student, cls, err = resolve_class_for_student_across_sessions(sessions, student_name, school)
            if err:
                return error("get_next_week_timetable", err)
            target_class = cls
        else:
            edu = sessions.get(school)
            if class_name:
                classes = edu.get_classes()
                matched = [c for c in classes if c.name.lower() == class_name.lower()]
                if not matched:
                    available = ", ".join(sorted(c.name for c in classes))
                    return error(
                        "get_next_week_timetable", f"Class '{class_name}' not found.",
                        f"Available classes: {available}",
                    )
                target_class = matched[0]

        result = {}
        for i in range(5):
            d = monday + timedelta(days=i)
            try:
                if target_class:
                    lessons = edu.get_timetable(target_class, d)
                else:
                    lessons = edu.get_my_timetable(d)
                result[d.isoformat()] = lean_timetable(lessons)
            except Exception as e:
                logger.debug("Error fetching timetable for %s: %s", d, e)
                result[d.isoformat()] = {"error": str(e)}
        return lean_json(result)

    @mcp.tool()
    @handle_errors("get_timetable_changes")
    def get_timetable_changes(date_str: str = "", school: str = "") -> str:
        """
        Get timetable changes / substitutions for a date (defaults to today).

        Args:
            date_str: Date in YYYY-MM-DD format. Leave empty for today.
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of timetable changes
        """
        target_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        )

        def _fetch(edu):
            changes = edu.get_timetable_changes(target_date)
            return [serialize(c) for c in changes]

        return lean_json(sessions.for_all(_fetch, school))
