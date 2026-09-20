"""School tools — get_classes, get_classrooms, get_subjects, get_periods, get_news, get_meals, send_message."""

import logging
from datetime import date, datetime
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..errors import error, handle_errors
from ..serializers import lean_class, lean_classroom, lean_json, lean_subject, serialize
from ..session import SessionManager

logger = logging.getLogger(__name__)


def register(mcp: FastMCP, sessions: SessionManager) -> None:

    @mcp.tool()
    @handle_errors("get_classes")
    def get_classes(school: str = "") -> str:
        """
        Get all classes in the school.

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean class records
        """
        def _fetch(edu):
            return [lean_class(c) for c in edu.get_classes()]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_classrooms")
    def get_classrooms(school: str = "") -> str:
        """
        Get all classrooms in the school.

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean classroom records
        """
        def _fetch(edu):
            return [lean_classroom(r) for r in edu.get_classrooms()]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_subjects")
    def get_subjects(school: str = "") -> str:
        """
        Get all subjects taught at the school.

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean subject records
        """
        def _fetch(edu):
            return [lean_subject(s) for s in edu.get_subjects()]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_periods")
    def get_periods(school: str = "") -> str:
        """
        Get school period / bell schedule information.

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of periods with start/end times
        """
        def _fetch_periods(edu):
            # Try the ringing times from session data
            zvonenia = None
            if hasattr(edu, "data") and isinstance(edu.data, dict):
                zvonenia = edu.data.get("zvonenia")

            if zvonenia and isinstance(zvonenia, list):
                periods = []
                for i, item in enumerate(zvonenia):
                    if isinstance(item, dict):
                        periods.append({
                            "period": i + 1,
                            "start": item.get("starttime", ""),
                            "end": item.get("endtime", ""),
                        })
                if periods:
                    return periods

            # Fallback: try the ringing API if available
            try:
                ringing = edu.get_ringing_times()
                if ringing:
                    result = []
                    for r in ringing:
                        result.append({
                            "type": r.type.value if hasattr(r.type, "value") else str(r.type),
                            "time": r.time.strftime("%H:%M") if getattr(r, "time", None) else None,
                        })
                    return result
            except Exception:
                pass
            return None

        all_sessions = sessions.get_all()
        if school:
            if school not in all_sessions:
                available = ", ".join(all_sessions.keys())
                return error("get_periods", f"School '{school}' not found. Available: {available}")
            all_sessions = {school: all_sessions[school]}

        if len(all_sessions) == 1:
            edu = next(iter(all_sessions.values()))
            result = _fetch_periods(edu)
            if result:
                return lean_json(result)
            return error(
                "get_periods",
                "Bell schedule data not available.",
                "The school may not have published period times.",
            )

        # Multi-school: nest under school keys
        combined = {}
        for sub, edu in all_sessions.items():
            try:
                result = _fetch_periods(edu)
                combined[sub] = result or {"message": "Bell schedule data not available."}
            except Exception as e:
                combined[sub] = {"error": str(e)}
        return lean_json(combined)

    @mcp.tool()
    @handle_errors("get_news")
    def get_news(school: str = "") -> str:
        """
        Get school news from the Edupage webpage.

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of news items
        """
        def _fetch(edu):
            news = edu.get_news()
            return [serialize(n) for n in news]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_meals")
    def get_meals(date_str: str = "", school: str = "") -> str:
        """
        Get school meal information.

        Args:
            date_str: Date in YYYY-MM-DD format. Leave empty for today.
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON of meal data (snack, lunch, afternoon_snack)
        """
        target_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
        )

        def _fetch_meals(edu):
            meals = edu.get_meals(target_date)
            if meals is None:
                return {}
            result = {}
            for slot in ("snack", "lunch", "afternoon_snack"):
                meal = getattr(meals, slot, None)
                if meal:
                    result[slot] = {
                        "title": getattr(meal, "title", None),
                        "date": meal.date.isoformat() if getattr(meal, "date", None) else None,
                        "served_from": meal.served_from.isoformat() if getattr(meal, "served_from", None) else None,
                        "served_to": meal.served_to.isoformat() if getattr(meal, "served_to", None) else None,
                        "ordered_meal": getattr(meal, "ordered_meal", None),
                        "menus": [
                            {
                                "name": getattr(m, "name", None),
                                "allergens": getattr(m, "allergens", None),
                                "weight": getattr(m, "weight", None),
                                "number": getattr(m, "number", None),
                            }
                            for m in (meal.menus or [])
                        ],
                    }
            return result

        all_sessions = sessions.get_all()
        if school:
            if school not in all_sessions:
                available = ", ".join(all_sessions.keys())
                return error("get_meals", f"School '{school}' not found. Available: {available}")
            all_sessions = {school: all_sessions[school]}

        if len(all_sessions) == 1:
            edu = next(iter(all_sessions.values()))
            result = _fetch_meals(edu)
            if not result:
                return lean_json({"message": "No meal data available for this date."})
            return lean_json(result)

        # Multi-school: nest under school keys
        combined = {}
        for sub, edu in all_sessions.items():
            try:
                result = _fetch_meals(edu)
                combined[sub] = result or {"message": "No meal data available for this date."}
            except Exception as e:
                combined[sub] = {"error": str(e)}
        return lean_json(combined)

    @mcp.tool()
    @handle_errors("send_message")
    def send_message(recipients: str, body: str, school: str = "") -> str:
        """
        Send a message to one or more Edupage users.
        ⚠️  Use with care – this sends real messages.

        Args:
            recipients: Comma-separated list of recipient names (must match teacher/student names exactly)
            body: The message text to send
            school: School subdomain (required when recipient exists in multiple schools).

        Returns:
            Success or error message
        """
        all_sessions = sessions.get_all()
        if school:
            if school not in all_sessions:
                available = ", ".join(all_sessions.keys())
                return error("send_message", f"School '{school}' not found. Available: {available}")
            all_sessions = {school: all_sessions[school]}

        recipient_names = [r.strip() for r in recipients.split(",")]

        # Build a people index: name → [(subdomain, edu, person)]
        people_index: dict[str, list[tuple[str, Any, Any]]] = {}
        for sub, edu in all_sessions.items():
            all_people: list[Any] = []
            try:
                all_people.extend(edu.get_teachers())
            except Exception:
                pass
            try:
                all_people.extend(edu.get_students())
            except Exception:
                pass
            for person in all_people:
                full_name = getattr(person, "name", "") or ""
                people_index.setdefault(full_name.lower(), []).append((sub, edu, person))

        # Resolve each recipient
        matched: list[tuple[str, Any, Any]] = []  # (subdomain, edu, person)
        not_found = []
        ambiguous = []
        for name in recipient_names:
            name_lower = name.lower()
            candidates = []
            for key, entries in people_index.items():
                if name_lower in key:
                    candidates.extend(entries)
            if not candidates:
                not_found.append(name)
            elif len(candidates) == 1:
                matched.append(candidates[0])
            else:
                # Check if all candidates are from the same school
                schools_found = {c[0] for c in candidates}
                if len(schools_found) == 1:
                    matched.append(candidates[0])
                else:
                    ambiguous.append(f"{name} (found in: {', '.join(schools_found)})")

        if not_found:
            return error("send_message", f"Could not find recipients: {', '.join(not_found)}")
        if ambiguous:
            return error(
                "send_message",
                f"Ambiguous recipients: {'; '.join(ambiguous)}. Specify the 'school' parameter.",
            )
        if not matched:
            return error("send_message", "No recipients matched.")

        # Group by session and send
        by_session: dict[str, tuple[Any, list[Any]]] = {}
        for sub, edu, person in matched:
            if sub not in by_session:
                by_session[sub] = (edu, [])
            by_session[sub][1].append(person)

        sent_names = []
        for sub, (edu, people) in by_session.items():
            edu.send_message(people, body)
            sent_names.extend(getattr(p, "name", str(p)) for p in people)

        return f"Message sent to: {', '.join(sent_names)}"
