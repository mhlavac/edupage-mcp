"""People tools — get_my_children, get_students, get_all_students, get_teachers."""

from mcp.server.fastmcp import FastMCP

from ..errors import handle_errors
from ..serializers import lean_json, lean_student, lean_teacher
from ..session import SessionManager


def register(mcp: FastMCP, sessions: SessionManager) -> None:

    @mcp.tool()
    @handle_errors("get_my_children")
    def get_my_children(school: str = "") -> str:
        """
        Get your children (for parent accounts) or classmates (for student accounts).
        Use this to find student names for use with other tools like get_timetable,
        get_absences, and get_student_summary.

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of students with person_id, name, class_id, number
        """
        def _fetch(edu):
            return [lean_student(s) for s in edu.get_students()]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_students")
    def get_students(school: str = "") -> str:
        """
        Get students in your class.

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean student records
        """
        def _fetch(edu):
            return [lean_student(s) for s in edu.get_students()]

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_all_students")
    def get_all_students(school: str = "") -> str:
        """
        Get all students in the school (name + class only).

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of student skeletons
        """
        def _fetch(edu):
            result = []
            for s in edu.get_all_students():
                result.append({
                    "person_id": getattr(s, "person_id", None),
                    "name": getattr(s, "name_short", None) or getattr(s, "name", None),
                    "class_id": getattr(s, "class_id", None),
                })
            return result

        return lean_json(sessions.for_all(_fetch, school))

    @mcp.tool()
    @handle_errors("get_teachers")
    def get_teachers(school: str = "") -> str:
        """
        Get all teachers in the school.

        Args:
            school: School subdomain (only needed with multiple schools).

        Returns:
            JSON array of lean teacher records
        """
        def _fetch(edu):
            return [lean_teacher(t) for t in edu.get_teachers()]

        return lean_json(sessions.for_all(_fetch, school))
