"""Timeline event filtering and categorization."""

from datetime import datetime

from .dates import extract_event_date

_SYSTEM_EVENT_TYPES: set[str] = {
    "h_attendance", "h_vcelicka", "h_clearcache", "h_cleardbi",
    "h_clearisicdata", "h_clearplany", "h_contest", "h_dailyplan",
    "h_edusettings", "h_financie", "h_znamky", "h_homework",
    "h_igroups", "h_process", "h_processtypes", "h_settings",
    "h_substitution", "h_timetable", "h_userphoto",
    "strava_kredit", "strava_vydaj", "h_stravamenu", "pipnutie",
}

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


def filter_timeline_events(
    events: list,
    *,
    include_system: bool = False,
    status: str = "",
    starred: str = "",
    event_type: str = "",
    category: str = "",
    date_from: str = "",
    date_to: str = "",
    by_event_date: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """Filter and paginate timeline events.

    Args:
        include_system: Include H_* and other system events (default False).
        status: "active", "done", or "" (all).
        starred: "yes", "no", or "" (all).
        event_type: Comma-separated raw type values (e.g. "homework,etesthw").
        category: Human-friendly category name (e.g. "homework", "grades").
                  Mutually exclusive with event_type.
        date_from: ISO date string for start of range.
        date_to: ISO date string for end of range.
        by_event_date: When True, the date range filter (date_from / date_to)
                  applies to the *parsed event date* (extract_event_date) rather
                  than the post timestamp. Useful for "event"-style items whose
                  real date lives in the title. Items whose event date cannot be
                  parsed fall back to their timestamp. Default False (backward
                  compatible — filters on timestamp).
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

        # Date range filter — on the parsed event date when requested,
        # otherwise on the post timestamp.
        ts = getattr(e, "timestamp", None)
        ref_date = None
        if by_event_date:
            ref_date = extract_event_date(e)
        if ref_date is None and ts:
            ref_date = ts.date() if isinstance(ts, datetime) else ts
        if ref_date:
            if dt_from and ref_date < dt_from:
                continue
            if dt_to and ref_date > dt_to:
                continue

        filtered.append(e)

    # Sort newest first
    filtered.sort(
        key=lambda e: getattr(e, "timestamp", datetime.min),
        reverse=True,
    )

    # Paginate
    return filtered[offset:offset + limit]
