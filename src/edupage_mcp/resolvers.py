"""Student and class resolution helpers."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .session import SessionManager

logger = logging.getLogger(__name__)


def resolve_student(edu: Any, student_name: str) -> tuple[Any, str]:
    """Resolve a student by name. Returns (student, error_msg).

    Exact case-insensitive match first, then substring.
    """
    students = edu.get_students()
    if not students:
        return None, "No students found. Are you logged in as a parent or student?"

    name_lower = student_name.lower()

    # Exact match
    for s in students:
        if getattr(s, "name", "").lower() == name_lower:
            return s, ""

    # Substring match
    matches = [s for s in students if name_lower in getattr(s, "name", "").lower()]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        names = ", ".join(getattr(s, "name", "?") for s in matches)
        return None, f"Ambiguous name '{student_name}'. Matches: {names}"

    available = ", ".join(getattr(s, "name", "?") for s in students)
    return None, f"Student '{student_name}' not found. Available: {available}"


def resolve_class_for_student(edu: Any, student_name: str) -> tuple[Any, Any, str]:
    """Resolve student then find their Class object.

    Returns (student, class_obj, error_msg).
    """
    student, err = resolve_student(edu, student_name)
    if err:
        return None, None, err

    class_id = getattr(student, "class_id", None)
    if not class_id:
        return student, None, f"Student '{student.name}' has no class_id."

    classes = edu.get_classes()
    class_by_id: dict[int, Any] = {}
    for c in classes:
        class_by_id[c.class_id] = c
        class_by_id[abs(c.class_id)] = c

    cls = class_by_id.get(class_id) or class_by_id.get(abs(class_id))
    if not cls:
        return student, None, f"Class ID {class_id} not found for student '{student.name}'."

    return student, cls, ""


# ---------------------------------------------------------------------------
# Cross-session resolution (multi-school)
# ---------------------------------------------------------------------------


def resolve_student_across_sessions(
    sessions: "SessionManager", student_name: str, school: str = ""
) -> tuple[Any, Any, str]:
    """Search all sessions for a student. Returns (edu, student, error_msg).

    If school specified, only search that session.
    If found in exactly one session, return it.
    If found in multiple, error asking to specify school.
    If not found, list all available students with their school.
    """
    all_sessions = sessions.get_all()
    if school:
        if school not in all_sessions:
            available = ", ".join(all_sessions.keys())
            return None, None, f"School '{school}' not found. Available: {available}"
        all_sessions = {school: all_sessions[school]}

    found: list[tuple[str, Any, Any]] = []  # (subdomain, edu, student)
    all_students: list[tuple[str, str]] = []  # (subdomain, student_name)

    for sub, edu in all_sessions.items():
        student, err = resolve_student(edu, student_name)
        if student:
            found.append((sub, edu, student))
        else:
            try:
                students = edu.get_students()
                for s in students:
                    all_students.append((sub, getattr(s, "name", "?")))
            except Exception:
                pass

    if len(found) == 1:
        return found[0][1], found[0][2], ""

    if len(found) > 1:
        schools = ", ".join(f[0] for f in found)
        return None, None, (
            f"Student '{student_name}' found in multiple schools: {schools}. "
            f"Specify the 'school' parameter."
        )

    # Not found anywhere
    available = ", ".join(f"{name} ({sub})" for sub, name in all_students)
    return None, None, f"Student '{student_name}' not found. Available: {available}"


def resolve_class_for_student_across_sessions(
    sessions: "SessionManager", student_name: str, school: str = ""
) -> tuple[Any, Any, Any, str]:
    """Resolve student across sessions then find their Class.

    Returns (edu, student, class_obj, error_msg).
    """
    edu, student, err = resolve_student_across_sessions(sessions, student_name, school)
    if err:
        return None, None, None, err

    _, cls, err = resolve_class_for_student(edu, student.name)
    if err:
        return edu, student, None, err

    return edu, student, cls, ""
