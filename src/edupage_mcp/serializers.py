"""Lean serializers for edupage-api data classes.

Each _lean_*() function extracts only useful fields, reducing response size
by ~90% compared to raw __dict__ dumps.
"""

import json
from datetime import date, datetime, time
from typing import Any

from .dates import extract_event_date


def serialize(obj: Any) -> Any:
    """Best-effort serializer for edupage-api data classes."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.strftime("%H:%M")
    if isinstance(obj, (list, tuple)):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {str(k): serialize(v) for k, v in obj.items()}
    if hasattr(obj, "__dict__"):
        return {
            k: serialize(v)
            for k, v in obj.__dict__.items()
            if not k.startswith("_")
        }
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


def to_json(obj: Any) -> str:
    """Serialize an edupage object to a JSON string."""
    return json.dumps(serialize(obj), indent=2, ensure_ascii=False, default=str)


def lean_json(data: Any) -> str:
    """Serialize lean data to a JSON string."""
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Lean serializers — flat, concise records
# ---------------------------------------------------------------------------


def lean_lesson(lesson: Any) -> dict:
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


def lean_timetable(lessons: Any) -> list[dict]:
    """Convert a list of Lesson objects (or Timetable) to lean dicts."""
    if hasattr(lessons, "lessons"):
        lessons = lessons.lessons
    if not lessons:
        return []
    return [lean_lesson(lesson) for lesson in lessons]


def lean_grade(grade: Any) -> dict:
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


def lean_student(student: Any) -> dict:
    """Flatten an EduStudent into a concise dict."""
    return {
        "person_id": getattr(student, "person_id", None),
        "name": getattr(student, "name", None),
        "class_id": getattr(student, "class_id", None),
        "number": getattr(student, "number_in_class", None),
    }


def lean_teacher(teacher: Any) -> dict:
    """Flatten an EduTeacher into a concise dict."""
    return {
        "person_id": getattr(teacher, "person_id", None),
        "name": getattr(teacher, "name", None),
        "classroom": getattr(teacher, "classroom_name", None),
    }


def lean_class(cls: Any) -> dict:
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


def lean_classroom(room: Any) -> dict:
    """Flatten a Classroom into a concise dict."""
    return {
        "classroom_id": getattr(room, "classroom_id", None),
        "name": getattr(room, "name", None),
        "short": getattr(room, "short", None),
    }


def lean_subject(subj: Any) -> dict:
    """Flatten a Subject into a concise dict."""
    return {
        "subject_id": getattr(subj, "subject_id", None),
        "name": getattr(subj, "name", None),
        "short": getattr(subj, "short", None),
    }


def lean_timeline_event(event: Any) -> dict:
    """Flatten a TimelineEvent into a concise dict."""
    author = getattr(event, "author", None)
    author_name = author.name if hasattr(author, "name") else str(author) if author else None
    event_type = getattr(event, "event_type", None)
    type_val = event_type.value if hasattr(event_type, "value") else str(event_type) if event_type else None
    result = {
        "event_id": getattr(event, "event_id", None),
        "type": type_val,
        "timestamp": event.timestamp.isoformat() if getattr(event, "timestamp", None) else None,
        "text": getattr(event, "text", None),
        "author": author_name,
        "is_done": getattr(event, "is_done", False),
        "is_starred": getattr(event, "is_starred", False),
        "created_at": event.created_at.isoformat() if getattr(event, "created_at", None) else None,
    }
    # Surface the real event date (parsed from the title) when present — distinct
    # from `timestamp`, which is when the announcement was posted.
    ev_date = extract_event_date(event)
    if ev_date is not None:
        result["event_date"] = ev_date.isoformat()
    return result


def additional_data(event: Any) -> dict:
    """Return an event's ``additional_data`` as a dict.

    Edupage sometimes hands back a list (or other non-mapping) here, which used
    to blow up every caller with ``'list' object has no attribute 'get'``.
    """
    ad = getattr(event, "additional_data", None)
    return ad if isinstance(ad, dict) else {}

def extract_homework_fields(event: Any) -> dict:
    """Extract homework-specific fields from a timeline event."""
    base = lean_timeline_event(event)
    ad = additional_data(event)

    title = (
        ad.get("nazov")
        or ad.get("title")
        or ad.get("name")
        or base.get("text", "")
    )

    subject = (
        ad.get("predmetNazov")
        or ad.get("nazov_predmetu")
        or ad.get("subject_name")
        or ad.get("predmet")
        or ""
    )

    due = ad.get("dateto") or ad.get("date_to") or ad.get("date") or ""

    base.update({
        "title": title,
        "subject": subject,
        "due_date": due,
    })
    return base


def extract_assignment_fields(event: Any) -> dict:
    """Extract assignment fields from a timeline event (broader than homework)."""
    base = extract_homework_fields(event)
    ad = additional_data(event)
    base.update({
        "max_points": ad.get("maxPoints") or ad.get("max_points"),
        "description": ad.get("popis") or ad.get("description") or "",
    })
    return base
