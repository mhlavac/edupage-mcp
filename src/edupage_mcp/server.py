"""
Edupage MCP Server

Exposes Edupage functionality (timetables, grades, messages, etc.)
as MCP tools for use with Claude Desktop, Claude Code, and Cowork.
"""

import functools
import json
import logging
import os
import sys
from datetime import date, datetime, time, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import of edupage_api – keeps startup fast and gives a clear error
# if the dependency is missing.
# ---------------------------------------------------------------------------
_edupage_api = None


def _get_edupage_api():
    global _edupage_api
    if _edupage_api is None:
        try:
            import edupage_api as _mod

            _edupage_api = _mod
        except ImportError:
            raise RuntimeError(
                "edupage-api is not installed. Run: pip install edupage-api"
            )
    return _edupage_api


# ---------------------------------------------------------------------------
# Session management – one Edupage instance per server process.
# ---------------------------------------------------------------------------
_session: Any = None


def _get_session():
    """Return the current logged-in Edupage session or raise."""
    if _session is None:
        raise RuntimeError(
            "Not logged in. Call the 'login' tool (no arguments needed — "
            "credentials are read from environment variables)."
        )
    return _session


# ---------------------------------------------------------------------------
# Generic serialiser (kept as fallback)
# ---------------------------------------------------------------------------


def _serialize(obj: Any) -> Any:
    """Best-effort serialiser for edupage-api data classes."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime("%H:%M")
    if isinstance(obj, (list, tuple)):
        return [_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "__dict__"):
        return {
            k: _serialize(v)
            for k, v in obj.__dict__.items()
            if not k.startswith("_")
        }
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


def _json(obj: Any) -> str:
    """Serialise an edupage object to a JSON string."""
    return json.dumps(_serialize(obj), indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Lean serialisers — flat, concise records (~90% smaller than __dict__ dump)
# ---------------------------------------------------------------------------


def _lean_lesson(lesson: Any) -> dict:
    """Flatten a Lesson into a concise dict."""
    return {
        "period": getattr(lesson, "period", None),
        "start": lesson.start_time.strftime("%H:%M") if getattr(lesson, "start_time", None) else None,
        "end": lesson.end_time.strftime("%H:%M") if getattr(lesson, "end_time", None) else None,
        "duration": getattr(lesson, "duration", None),
        "subject": getattr(lesson.subject, "short", None) if getattr(lesson, "subject", None) else None,
        "subject_name": getattr(lesson.subject, "name", None) if getattr(lesson, "subject", None) else None,
        "teachers": [t.name for t in (lesson.teachers or [])],
        "classrooms": [getattr(c, "short", c.name) for c in (lesson.classrooms or [])],
        "groups": lesson.groups or [],
        "cancelled": getattr(lesson, "is_cancelled", False),
        "is_event": getattr(lesson, "is_event", False),
        "curriculum": getattr(lesson, "curriculum", None),
        "online_lesson_link": getattr(lesson, "online_lesson_link", None),
    }


def _lean_timetable(lessons: Any) -> list[dict]:
    """Convert a list of Lesson objects (or Timetable) to lean dicts."""
    if hasattr(lessons, "lessons"):
        lessons = lessons.lessons
    if not lessons:
        return []
    return [_lean_lesson(lesson) for lesson in lessons]


def _lean_grade(grade: Any) -> dict:
    """Flatten an EduGrade into a concise dict."""
    return {
        "event_id": getattr(grade, "event_id", None),
        "title": getattr(grade, "title", None),
        "grade": getattr(grade, "grade_n", None),
        "comment": getattr(grade, "comment", None),
        "date": grade.date.isoformat() if getattr(grade, "date", None) else None,
        "subject": getattr(grade, "subject_name", None),
        "subject_id": getattr(grade, "subject_id", None),
        "teacher": grade.teacher.name if getattr(grade, "teacher", None) else None,
        "max_points": getattr(grade, "max_points", None),
        "importance": getattr(grade, "importance", None),
        "verbal": getattr(grade, "verbal", None),
        "percent": getattr(grade, "percent", None),
        "class_avg": getattr(grade, "class_grade_avg", None),
    }


def _lean_student(student: Any) -> dict:
    """Flatten an EduStudent into a concise dict."""
    return {
        "person_id": getattr(student, "person_id", None),
        "name": getattr(student, "name", None),
        "class_id": getattr(student, "class_id", None),
        "number": getattr(student, "number_in_class", None),
    }


def _lean_teacher(teacher: Any) -> dict:
    """Flatten an EduTeacher into a concise dict."""
    return {
        "person_id": getattr(teacher, "person_id", None),
        "name": getattr(teacher, "name", None),
        "classroom": getattr(teacher, "classroom_name", None),
    }


def _lean_class(cls: Any) -> dict:
    """Flatten a Class into a concise dict."""
    return {
        "class_id": getattr(cls, "class_id", None),
        "name": getattr(cls, "name", None),
        "short": getattr(cls, "short", None),
        "grade": getattr(cls, "grade", None),
        "homeroom_teachers": (
            [t.name for t in (cls.homeroom_teachers or [])]
            if getattr(cls, "homeroom_teachers", None) else []
        ),
    }


def _lean_classroom(room: Any) -> dict:
    """Flatten a Classroom into a concise dict."""
    return {
        "classroom_id": getattr(room, "classroom_id", None),
        "name": getattr(room, "name", None),
        "short": getattr(room, "short", None),
    }


def _lean_subject(subj: Any) -> dict:
    """Flatten a Subject into a concise dict."""
    return {
        "subject_id": getattr(subj, "subject_id", None),
        "name": getattr(subj, "name", None),
        "short": getattr(subj, "short", None),
    }


def _lean_timeline_event(event: Any) -> dict:
    """Flatten a TimelineEvent into a concise dict."""
    author = getattr(event, "author", None)
    author_name = author.name if hasattr(author, "name") else str(author) if author else None
    event_type = getattr(event, "event_type", None)
    type_val = event_type.value if hasattr(event_type, "value") else str(event_type) if event_type else None
    return {
        "event_id": getattr(event, "event_id", None),
        "type": type_val,
        "timestamp": event.timestamp.isoformat() if getattr(event, "timestamp", None) else None,
        "text": getattr(event, "text", None),
        "author": author_name,
        "is_done": getattr(event, "is_done", False),
        "is_starred": getattr(event, "is_starred", False),
        "created_at": event.created_at.isoformat() if getattr(event, "created_at", None) else None,
    }


def _lean_json(data: Any) -> str:
    """Serialise lean data to a JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

_ERROR_HINTS: dict[str, str] = {
    "BadCredentialsException": "Wrong username or password. Check EDUPAGE_USERNAME and EDUPAGE_PASSWORD.",
    "CaptchaException": "Edupage is requesting a CAPTCHA. Log in via browser first, then retry.",
    "NotLoggedInException": "Not logged in. Call the 'login' tool first.",
    "RuntimeError": "Check that you are logged in (call 'login' tool).",
    "ConnectionError": "Network error. Check your internet connection.",
    "TimeoutError": "Request timed out. Edupage may be slow — try again.",
}


def _error(action: str, detail: str, hint: str = "") -> str:
    """Return a structured JSON error string."""
    err: dict[str, Any] = {"error": True, "action": action, "detail": detail}
    if hint:
        err["hint"] = hint
    return json.dumps(err, ensure_ascii=False)


def _handle_errors(action: str):
    """Decorator that catches exceptions and returns structured error JSON."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                exc_name = type(e).__name__
                hint = _ERROR_HINTS.get(exc_name, "")
                logger.exception("Error in %s: %s", action, e)
                return _error(action, str(e), hint)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# System event types to filter from timeline
# ---------------------------------------------------------------------------

_SYSTEM_EVENT_TYPES: set[str] = {
    "h_attendance", "h_vcelicka", "h_clearcache", "h_cleardbi",
    "h_clearisicdata", "h_clearplany", "h_contest", "h_dailyplan",
    "h_edusettings", "h_financie", "h_znamky", "h_homework",
    "h_igroups", "h_process", "h_processtypes", "h_settings",
    "h_substitution", "h_timetable", "h_userphoto",
    "strava_kredit", "strava_vydaj", "h_stravamenu", "pipnutie",
}


# ---------------------------------------------------------------------------
# Event categories — human-friendly names → raw event type values
# ---------------------------------------------------------------------------

_EVENT_CATEGORIES: dict[str, list[str]] = {
    "homework": ["homework", "etesthw"],
    "grades": ["znamka", "znamkydoc"],
    "exams": ["bexam", "sexam", "oexam", "rexam", "pexam", "testing"],
    "messages": ["sprava"],
    "absences": ["student_absent", "ospravedlnenka"],
    "events": [
        "event", "schoolevent", "excursion", "trip", "culture",
        "parentsevening", "meeting", "bmeeting",
    ],
    "news": ["news"],
}


def _filter_timeline_events(
    events: list,
    *,
    include_system: bool = False,
    status: str = "",
    starred: str = "",
    event_type: str = "",
    category: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list:
    """
    Filter and paginate timeline events.

    Args:
        include_system: Include H_* and other system events (default False).
        status: "active", "done", or "" (all).
        starred: "yes", "no", or "" (all).
        event_type: Comma-separated raw type values (e.g. "homework,etesthw").
        category: Human-friendly category name (e.g. "homework", "grades").
                  Mutually exclusive with event_type.
        date_from: ISO date string for start of range.
        date_to: ISO date string for end of range.
        limit: Max events to return (default 50).
        offset: Number of events to skip (for pagination).
    """
    # Expand category to event_type list
    type_filter: set[str] | None = None
    if category and category in _EVENT_CATEGORIES:
        type_filter = set(_EVENT_CATEGORIES[category])
    elif event_type:
        type_filter = {t.strip() for t in event_type.split(",")}

    # Parse date range
    dt_from = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
    dt_to = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None

    filtered = []
    for e in events:
        # Skip removed
        if getattr(e, "is_removed", False):
            continue

        # Skip system events unless requested
        if not include_system:
            et = getattr(e, "event_type", None)
            type_val = et.value if hasattr(et, "value") else str(et) if et else ""
            if type_val in _SYSTEM_EVENT_TYPES:
                continue

        # Status filter
        if status == "active" and getattr(e, "is_done", False):
            continue
        if status == "done" and not getattr(e, "is_done", False):
            continue

        # Starred filter
        if starred == "yes" and not getattr(e, "is_starred", False):
            continue
        if starred == "no" and getattr(e, "is_starred", False):
            continue

        # Event type filter
        if type_filter:
            et = getattr(e, "event_type", None)
            type_val = et.value if hasattr(et, "value") else str(et) if et else ""
            if type_val not in type_filter:
                continue

        # Date range filter
        ts = getattr(e, "timestamp", None)
        if ts:
            event_date = ts.date() if isinstance(ts, datetime) else ts
            if dt_from and event_date < dt_from:
                continue
            if dt_to and event_date > dt_to:
                continue

        filtered.append(e)

    # Sort newest first
    filtered.sort(
        key=lambda e: getattr(e, "timestamp", datetime.min),
        reverse=True,
    )

    # Paginate
    return filtered[offset:offset + limit]


# ---------------------------------------------------------------------------
# Student resolution helpers
# ---------------------------------------------------------------------------


def _resolve_student(edu: Any, student_name: str) -> tuple[Any, str]:
    """
    Resolve a student by name. Returns (student, error_msg).
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


def _resolve_class_for_student(edu: Any, student_name: str) -> tuple[Any, Any, str]:
    """
    Resolve student then find their Class object.
    Returns (student, class_obj, error_msg).
    """
    student, err = _resolve_student(edu, student_name)
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
# Homework / assignment extraction from timeline events
# ---------------------------------------------------------------------------


def _extract_homework_fields(event: Any) -> dict:
    """Extract homework-specific fields from a timeline event."""
    base = _lean_timeline_event(event)
    ad = getattr(event, "additional_data", {}) or {}

    # Title: try multiple known keys
    title = (
        ad.get("nazov")
        or ad.get("title")
        or ad.get("name")
        or base.get("text", "")
    )

    # Subject
    subject = (
        ad.get("predmetNazov")
        or ad.get("nazov_predmetu")
        or ad.get("subject_name")
        or ad.get("predmet")
        or ""
    )

    # Due date
    due = ad.get("dateto") or ad.get("date_to") or ad.get("date") or ""

    base.update({
        "title": title,
        "subject": subject,
        "due_date": due,
    })
    return base


def _extract_assignment_fields(event: Any) -> dict:
    """Extract assignment fields from a timeline event (broader than homework)."""
    base = _extract_homework_fields(event)
    ad = getattr(event, "additional_data", {}) or {}
    base.update({
        "max_points": ad.get("maxPoints") or ad.get("max_points"),
        "description": ad.get("popis") or ad.get("description") or "",
    })
    return base


# ---------------------------------------------------------------------------
# MCP server definition
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "Edupage",
    instructions=(
        "MCP server for Edupage — a school information system. "
        "Authentication is handled automatically via environment variables "
        "(EDUPAGE_USERNAME, EDUPAGE_PASSWORD, EDUPAGE_SUBDOMAIN). "
        "If not already logged in, call the 'login' tool with no arguments. "
        "Never ask the user for credentials — they must be set as env vars. "
        "Tools expose timetables, grades, homework, messages, students, "
        "teachers, classes, and more. Use get_my_children() to find student "
        "names, then pass student_name to other tools for targeted lookups."
    ),
)


# ── Authentication ─────────────────────────────────────────────────────────


@mcp.tool()
def login(username: str = "", password: str = "", subdomain: str = "") -> str:
    """
    Log in to Edupage using environment variables. No parameters needed
    if EDUPAGE_USERNAME, EDUPAGE_PASSWORD, and EDUPAGE_SUBDOMAIN are set.

    Args:
        username: Your Edupage username (defaults to EDUPAGE_USERNAME env var)
        password: Your Edupage password (defaults to EDUPAGE_PASSWORD env var)
        subdomain: Your school's Edupage subdomain (defaults to EDUPAGE_SUBDOMAIN env var)

    Returns:
        Success or error message
    """
    global _session
    username = username or os.environ.get("EDUPAGE_USERNAME", "")
    password = password or os.environ.get("EDUPAGE_PASSWORD", "")
    subdomain = subdomain or os.environ.get("EDUPAGE_SUBDOMAIN", "")

    if not username or not password or not subdomain:
        missing = [
            name
            for name, val in [
                ("EDUPAGE_USERNAME", username),
                ("EDUPAGE_PASSWORD", password),
                ("EDUPAGE_SUBDOMAIN", subdomain),
            ]
            if not val
        ]
        return _error(
            "login", f"Missing environment variable(s): {', '.join(missing)}",
            "Set them before starting the server.",
        )

    api = _get_edupage_api()
    edu = api.Edupage()
    try:
        edu.login(username, password, subdomain)
    except api.exceptions.BadCredentialsException:
        return _error("login", "Wrong username or password.", _ERROR_HINTS["BadCredentialsException"])
    except api.exceptions.CaptchaException:
        return _error("login", "CAPTCHA requested.", _ERROR_HINTS["CaptchaException"])
    except Exception as e:
        return _error("login", str(e))
    _session = edu
    return f"Logged in successfully on {subdomain}.edupage.org"


@mcp.tool()
def login_auto(username: str = "", password: str = "") -> str:
    """
    Log in to Edupage via the portal (auto-detect school).
    No parameters needed if EDUPAGE_USERNAME and EDUPAGE_PASSWORD are set.

    Args:
        username: Your Edupage username / email (defaults to EDUPAGE_USERNAME env var)
        password: Your Edupage password (defaults to EDUPAGE_PASSWORD env var)

    Returns:
        Success or error message
    """
    global _session
    username = username or os.environ.get("EDUPAGE_USERNAME", "")
    password = password or os.environ.get("EDUPAGE_PASSWORD", "")

    if not username or not password:
        missing = [
            name
            for name, val in [
                ("EDUPAGE_USERNAME", username),
                ("EDUPAGE_PASSWORD", password),
            ]
            if not val
        ]
        return _error(
            "login_auto", f"Missing environment variable(s): {', '.join(missing)}",
            "Set them before starting the server.",
        )

    api = _get_edupage_api()
    edu = api.Edupage()
    try:
        edu.login_auto(username, password)
    except Exception as e:
        return _error("login_auto", str(e))
    _session = edu
    return "Logged in successfully via portal."


# ── Timetable ──────────────────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_timetable")
def get_timetable(date_str: str = "", class_name: str = "", student_name: str = "") -> str:
    """
    Get the timetable for a given date (defaults to today).

    Args:
        date_str: Date in YYYY-MM-DD format. Leave empty for today.
        class_name: Class name (e.g. '6e', '4a'). If empty, uses logged-in user's timetable.
        student_name: Student name to look up their class timetable (e.g. 'Jan Novak').
                      Resolves the student's class automatically.

    Returns:
        JSON array of lean timetable lessons
    """
    edu = _get_session()
    target_date = (
        datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    )

    # Resolve student → class
    if student_name:
        _student, cls, err = _resolve_class_for_student(edu, student_name)
        if err:
            return _error("get_timetable", err)
        timetable = edu.get_timetable(cls, target_date)
        return _lean_json(_lean_timetable(timetable))

    # If a class name is specified, look it up directly
    if class_name:
        return _get_timetable_by_class(edu, class_name, target_date)

    # Try the logged-in user's own timetable first
    try:
        timetable = edu.get_my_timetable(target_date)
        return _lean_json(_lean_timetable(timetable))
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
                        return _lean_json(_lean_timetable(timetable))
                    except Exception:
                        continue
    except Exception:
        pass

    return _error(
        "get_timetable", "Could not fetch timetable.",
        "Try specifying student_name or class_name (e.g. '4a').",
    )


def _get_timetable_by_class(edu: Any, class_name: str, target_date: date) -> str:
    """Fetch timetable for a specific class by name."""
    classes = edu.get_classes()
    matched = [c for c in classes if c.name.lower() == class_name.lower()]
    if not matched:
        available = ", ".join(sorted(c.name for c in classes))
        return _error("get_timetable", f"Class '{class_name}' not found.", f"Available classes: {available}")
    timetable = edu.get_timetable(matched[0], target_date)
    return _lean_json(_lean_timetable(timetable))


@mcp.tool()
@_handle_errors("get_next_week_timetable")
def get_next_week_timetable(class_name: str = "", student_name: str = "") -> str:
    """
    Get timetable for each day of the upcoming week (Mon-Fri).

    Args:
        class_name: Class name (e.g. '6e', '4a'). If empty, uses logged-in user's timetable.
        student_name: Student name to look up their class timetable.

    Returns:
        JSON object keyed by date with lean timetable lessons
    """
    edu = _get_session()
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    monday = today + timedelta(days=days_until_monday)

    # Resolve target class
    target_class = None
    if student_name:
        _student, cls, err = _resolve_class_for_student(edu, student_name)
        if err:
            return _error("get_next_week_timetable", err)
        target_class = cls
    elif class_name:
        classes = edu.get_classes()
        matched = [c for c in classes if c.name.lower() == class_name.lower()]
        if not matched:
            available = ", ".join(sorted(c.name for c in classes))
            return _error(
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
            result[d.isoformat()] = _lean_timetable(lessons)
        except Exception as e:
            logger.debug("Error fetching timetable for %s: %s", d, e)
            result[d.isoformat()] = {"error": str(e)}
    return _lean_json(result)


@mcp.tool()
@_handle_errors("get_timetable_changes")
def get_timetable_changes(date_str: str = "") -> str:
    """
    Get timetable changes / substitutions for a date (defaults to today).

    Args:
        date_str: Date in YYYY-MM-DD format. Leave empty for today.

    Returns:
        JSON array of timetable changes
    """
    edu = _get_session()
    target_date = (
        datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    )
    changes = edu.get_timetable_changes(target_date)
    return _json(changes)


# ── Grades ─────────────────────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_grades")
def get_grades(term: str = "", year: int = 0) -> str:
    """
    Get student grades/marks. Returns grades for the current session's child.
    For parent accounts with multiple children, grades are for the child linked
    to the current session.

    Args:
        term: Term/semester filter (leave empty for all)
        year: School year filter (leave 0 for current)

    Returns:
        JSON array of lean grade records with percent, class_avg, etc.
    """
    edu = _get_session()
    kwargs: dict[str, Any] = {}
    if term:
        kwargs["term"] = term
    if year:
        kwargs["year"] = year
    grades = edu.get_grades(**kwargs)
    return _lean_json([_lean_grade(g) for g in grades])


# ── Students & Teachers ───────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_my_children")
def get_my_children() -> str:
    """
    Get your children (for parent accounts) or classmates (for student accounts).
    Use this to find student names for use with other tools like get_timetable,
    get_absences, and get_student_summary.

    Returns:
        JSON array of students with person_id, name, class_id, number
    """
    edu = _get_session()
    students = edu.get_students()
    return _lean_json([_lean_student(s) for s in students])


@mcp.tool()
@_handle_errors("get_students")
def get_students() -> str:
    """
    Get students in your class.

    Returns:
        JSON array of lean student records
    """
    edu = _get_session()
    return _lean_json([_lean_student(s) for s in edu.get_students()])


@mcp.tool()
@_handle_errors("get_all_students")
def get_all_students() -> str:
    """
    Get all students in the school (name + class only).

    Returns:
        JSON array of student skeletons
    """
    edu = _get_session()
    students = edu.get_all_students()
    result = []
    for s in students:
        result.append({
            "person_id": getattr(s, "person_id", None),
            "name": getattr(s, "name_short", None) or getattr(s, "name", None),
            "class_id": getattr(s, "class_id", None),
        })
    return _lean_json(result)


@mcp.tool()
@_handle_errors("get_teachers")
def get_teachers() -> str:
    """
    Get all teachers in the school.

    Returns:
        JSON array of lean teacher records
    """
    edu = _get_session()
    return _lean_json([_lean_teacher(t) for t in edu.get_teachers()])


# ── Classes & Classrooms ──────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_classes")
def get_classes() -> str:
    """
    Get all classes in the school.

    Returns:
        JSON array of lean class records
    """
    edu = _get_session()
    return _lean_json([_lean_class(c) for c in edu.get_classes()])


@mcp.tool()
@_handle_errors("get_classrooms")
def get_classrooms() -> str:
    """
    Get all classrooms in the school.

    Returns:
        JSON array of lean classroom records
    """
    edu = _get_session()
    return _lean_json([_lean_classroom(r) for r in edu.get_classrooms()])


# ── Homework & Assignments ────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_homework")
def get_homework(since_days: int = 30, status: str = "") -> str:
    """
    Get homework assignments from the last N days.
    Extracts homework from the timeline/notification history.

    Args:
        since_days: How many days back to search (default 30)
        status: Filter by status — "active" (not done), "done", or "" (all, default)

    Returns:
        JSON array of homework items with title, subject, due_date, etc.
    """
    edu = _get_session()
    since = date.today() - timedelta(days=since_days)
    events = edu.get_notification_history(since)
    events = _filter_timeline_events(
        events,
        event_type="homework,etesthw",
        status=status,
        limit=200,
    )
    return _lean_json([_extract_homework_fields(e) for e in events])


@mcp.tool()
@_handle_errors("get_assignments")
def get_assignments(since_days: int = 30, status: str = "", event_type: str = "") -> str:
    """
    Get all assignments (homework, tests, exams, projects, etc.) from the last N days.

    Args:
        since_days: How many days back to search (default 30)
        status: Filter by status — "active", "done", or "" (all, default)
        event_type: Narrow to specific types (comma-separated). Valid types:
                    homework, etesthw, bexam, sexam, oexam, rexam, pexam, testing

    Returns:
        JSON array of assignment items
    """
    edu = _get_session()
    since = date.today() - timedelta(days=since_days)
    events = edu.get_notification_history(since)
    types = event_type or "homework,etesthw,bexam,sexam,oexam,rexam,pexam,testing"
    events = _filter_timeline_events(
        events,
        event_type=types,
        status=status,
        limit=200,
    )
    return _lean_json([_extract_assignment_fields(e) for e in events])


# ── Timeline & Notifications ─────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_timeline")
def get_timeline(
    status: str = "active",
    starred: str = "",
    event_type: str = "",
    category: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
    offset: int = 0,
    include_system: bool = False,
) -> str:
    """
    Get the visible timeline (recent messages, assignments, grades).
    System events (H_* types) are hidden by default.

    Args:
        status: Filter by status — "active" (default), "done", or "all".
        starred: Filter by starred — "yes", "no", or "" (all).
        event_type: Raw type filter (comma-separated, e.g. "sprava,znamka").
        category: Human-friendly category. One of: homework, grades, exams,
                  messages, absences, events, news. Mutually exclusive with event_type.
        date_from: Start date (YYYY-MM-DD) for date range filter.
        date_to: End date (YYYY-MM-DD) for date range filter.
        limit: Max items to return (default 50).
        offset: Items to skip for pagination.
        include_system: Include system events like H_* types (default false).

    Returns:
        JSON array of lean timeline events
    """
    edu = _get_session()
    events = edu.get_notifications()
    events = _filter_timeline_events(
        events,
        include_system=include_system,
        status="" if status == "all" else status,
        starred=starred,
        event_type=event_type,
        category=category,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return _lean_json([_lean_timeline_event(e) for e in events])


@mcp.tool()
@_handle_errors("get_notifications")
def get_notifications(
    status: str = "",
    starred: str = "",
    event_type: str = "",
    category: str = "",
    limit: int = 50,
    offset: int = 0,
    include_system: bool = False,
) -> str:
    """
    Get recent notifications. System events are hidden by default.

    Args:
        status: Filter — "active", "done", or "" (all, default).
        starred: Filter — "yes", "no", or "" (all).
        event_type: Raw type filter (comma-separated).
        category: Category filter: homework, grades, exams, messages, absences, events, news.
        limit: Max items (default 50).
        offset: Skip items for pagination.
        include_system: Include system events (default false).

    Returns:
        JSON array of lean notification events
    """
    edu = _get_session()
    events = edu.get_notifications()
    events = _filter_timeline_events(
        events,
        include_system=include_system,
        status=status,
        starred=starred,
        event_type=event_type,
        category=category,
        limit=limit,
        offset=offset,
    )
    return _lean_json([_lean_timeline_event(e) for e in events])


@mcp.tool()
@_handle_errors("get_notification_history")
def get_notification_history(
    since_date: str = "",
    status: str = "",
    starred: str = "",
    event_type: str = "",
    category: str = "",
    limit: int = 50,
    offset: int = 0,
    include_system: bool = False,
) -> str:
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

    Returns:
        JSON array of lean notification events
    """
    edu = _get_session()
    dt = datetime.strptime(since_date, "%Y-%m-%d").date() if since_date else date.today() - timedelta(days=7)
    events = edu.get_notification_history(dt)
    events = _filter_timeline_events(
        events,
        include_system=include_system,
        status=status,
        starred=starred,
        event_type=event_type,
        category=category,
        limit=limit,
        offset=offset,
    )
    return _lean_json([_lean_timeline_event(e) for e in events])


# ── News ──────────────────────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_news")
def get_news() -> str:
    """
    Get school news from the Edupage webpage.

    Returns:
        JSON array of news items
    """
    edu = _get_session()
    return _json(edu.get_news())


# ── Meals ─────────────────────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_meals")
def get_meals(date_str: str = "") -> str:
    """
    Get school meal information for a given date (defaults to today).

    Args:
        date_str: Date in YYYY-MM-DD format. Leave empty for today.

    Returns:
        JSON of meal data (snack, lunch, afternoon_snack)
    """
    edu = _get_session()
    target_date = (
        datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    )
    meals = edu.get_meals(target_date)
    if meals is None:
        return _lean_json({"message": "No meal data available for this date."})
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
    return _lean_json(result)


# ── Messaging ─────────────────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("send_message")
def send_message(recipients: str, body: str) -> str:
    """
    Send a message to one or more Edupage users.
    ⚠️  Use with care – this sends real messages.

    Args:
        recipients: Comma-separated list of recipient names (must match teacher/student names exactly)
        body: The message text to send

    Returns:
        Success or error message
    """
    edu = _get_session()
    recipient_names = [r.strip() for r in recipients.split(",")]

    all_people: list[Any] = []
    try:
        all_people.extend(edu.get_teachers())
    except Exception:
        pass
    try:
        all_people.extend(edu.get_students())
    except Exception:
        pass

    matched = []
    not_found = []
    for name in recipient_names:
        found = False
        for person in all_people:
            full_name = getattr(person, "name", "") or ""
            if name.lower() in full_name.lower():
                matched.append(person)
                found = True
                break
        if not found:
            not_found.append(name)

    if not_found:
        return _error("send_message", f"Could not find recipients: {', '.join(not_found)}")
    if not matched:
        return _error("send_message", "No recipients matched.")

    edu.send_message(matched, body)
    names = [getattr(p, "name", str(p)) for p in matched]
    return f"Message sent to: {', '.join(names)}"


# ── Absences ──────────────────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_absences")
def get_absences(since_days: int = 30, student_name: str = "") -> str:
    """
    Get absence records from the last N days.

    Args:
        since_days: How many days back to search (default 30)
        student_name: Optional student name to validate context (e.g. 'Jan Novak')

    Returns:
        JSON array of absence records with date, type, text, author
    """
    edu = _get_session()

    if student_name:
        _student, err = _resolve_student(edu, student_name)
        if err:
            return _error("get_absences", err)

    since = date.today() - timedelta(days=since_days)
    events = edu.get_notification_history(since)
    events = _filter_timeline_events(
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
    return _lean_json(result)


# ── Upcoming Events ──────────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_upcoming_events")
def get_upcoming_events(days_ahead: int = 30) -> str:
    """
    Get upcoming events and exams within the next N days.

    Args:
        days_ahead: How many days ahead to look (default 30)

    Returns:
        JSON array of upcoming events sorted by date (nearest first)
    """
    edu = _get_session()
    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)

    # Fetch recent + upcoming from notification history
    since = date.today() - timedelta(days=7)  # include recently created future events
    events = edu.get_notification_history(since)

    event_types = (
        "event,schoolevent,excursion,trip,culture,parentsevening,meeting,bmeeting,"
        "bexam,sexam,oexam,rexam,pexam,testing"
    )
    events = _filter_timeline_events(
        events,
        event_type=event_types,
        limit=500,
    )

    # Keep only future events
    upcoming = []
    for e in events:
        ts = getattr(e, "timestamp", None)
        if ts and ts >= now and ts <= cutoff:
            ad = getattr(e, "additional_data", {}) or {}
            et = getattr(e, "event_type", None)
            type_val = et.value if hasattr(et, "value") else str(et) if et else None
            title = ad.get("nazov") or ad.get("title") or getattr(e, "text", "")
            upcoming.append({
                "event_id": getattr(e, "event_id", None),
                "type": type_val,
                "date": ts.isoformat(),
                "title": title,
                "text": getattr(e, "text", None),
                "is_done": getattr(e, "is_done", False),
            })

    # Sort nearest first
    upcoming.sort(key=lambda x: x["date"])
    return _lean_json(upcoming)


# ── Student Summary ──────────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_student_summary")
def get_student_summary(student_name: str = "", since_days: int = 14) -> str:
    """
    Get a comprehensive summary for a student: grades, homework, exams,
    absences, and messages — all in one call.

    Args:
        student_name: Student name (e.g. 'Jan Novak'). Use get_my_children() to find names.
        since_days: How many days back to include (default 14)

    Returns:
        JSON object with student, class, grades, homework, exams, absences, messages
    """
    edu = _get_session()

    student_info = None
    class_info = None

    if student_name:
        student, cls, err = _resolve_class_for_student(edu, student_name)
        if err:
            return _error("get_student_summary", err)
        student_info = _lean_student(student)
        class_info = _lean_class(cls) if cls else None

    # Fetch notification history once
    since = date.today() - timedelta(days=since_days)
    events = edu.get_notification_history(since)

    # Partition by type
    homework_events = _filter_timeline_events(events, event_type="homework,etesthw", limit=100)
    exam_events = _filter_timeline_events(events, event_type="bexam,sexam,oexam,rexam,pexam,testing", limit=100)
    absence_events = _filter_timeline_events(events, event_type="student_absent,ospravedlnenka", limit=100)
    message_events = _filter_timeline_events(events, event_type="sprava", limit=50)

    # Fetch grades separately (richer data)
    try:
        grades = edu.get_grades()
        # Filter to recent grades
        grade_list = []
        for g in grades:
            g_date = getattr(g, "date", None)
            if g_date:
                g_date_val = g_date.date() if isinstance(g_date, datetime) else g_date
                if g_date_val >= since:
                    grade_list.append(_lean_grade(g))
            else:
                grade_list.append(_lean_grade(g))
    except Exception:
        grade_list = []

    summary = {
        "student": student_info,
        "class": class_info,
        "period": f"last {since_days} days (since {since.isoformat()})",
        "grades": grade_list,
        "homework": [_extract_homework_fields(e) for e in homework_events],
        "exams": [_lean_timeline_event(e) for e in exam_events],
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
        "messages": [_lean_timeline_event(e) for e in message_events],
    }
    return _lean_json(summary)


# ── School info helpers ───────────────────────────────────────────────────


@mcp.tool()
@_handle_errors("get_subjects")
def get_subjects() -> str:
    """
    Get all subjects taught at the school.

    Returns:
        JSON array of lean subject records
    """
    edu = _get_session()
    return _lean_json([_lean_subject(s) for s in edu.get_subjects()])


@mcp.tool()
@_handle_errors("get_periods")
def get_periods() -> str:
    """
    Get school period / bell schedule information.

    Returns:
        JSON array of periods with start/end times
    """
    edu = _get_session()

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
            return _lean_json(periods)

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
            return _lean_json(result)
    except Exception:
        pass

    return _error("get_periods", "Bell schedule data not available.", "The school may not have published period times.")


# ---------------------------------------------------------------------------
# Auto-login from environment variables
# ---------------------------------------------------------------------------


def _try_env_login():
    """Attempt to log in using environment variables at startup."""
    global _session
    username = os.environ.get("EDUPAGE_USERNAME")
    password = os.environ.get("EDUPAGE_PASSWORD")
    subdomain = os.environ.get("EDUPAGE_SUBDOMAIN")

    if username and password and subdomain:
        api = _get_edupage_api()
        edu = api.Edupage()
        try:
            edu.login(username, password, subdomain)
            _session = edu
            logger.info("Auto-logged in as %s on %s", username, subdomain)
        except Exception as e:
            logger.warning("Auto-login failed: %s", e)
    elif username and password:
        api = _get_edupage_api()
        edu = api.Edupage()
        try:
            edu.login_auto(username, password)
            _session = edu
            logger.info("Auto-logged in as %s via portal", username)
        except Exception as e:
            logger.warning("Auto-login via portal failed: %s", e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _try_env_login()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
