# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

MCP server that connects Claude to Edupage — a school information system used across Europe. Modular Python package (`src/edupage_mcp/`) exposing ~25 tools via the FastMCP framework. Built on top of the `edupage-api` library.

## Development Commands

```bash
# Install dependencies
uv sync

# Run the server (stdio transport)
uv run python -m edupage_mcp

# Test with MCP Inspector
npx @modelcontextprotocol/inspector uv run python -m edupage_mcp

# Run tests
uv run pytest tests/
```

## Architecture

The package is structured as focused modules under `src/edupage_mcp/`:

```
src/edupage_mcp/
├── __init__.py          # re-export main()
├── __main__.py          # python -m entry
├── app.py               # FastMCP creation, auto-login, main()
├── session.py           # SessionManager class
├── serializers.py       # lean_* + serialize + to_json
├── errors.py            # handle_errors, _ERROR_HINTS, error()
├── dates.py             # extract_event_date — real event date from title/structured field
├── filters.py           # filter_timeline_events, categories, system events
├── resolvers.py         # student/class resolution (single + cross-session)
└── tools/
    ├── __init__.py      # register_all(mcp, sessions)
    ├── auth.py          # login, login_auto
    ├── timetable.py     # get_timetable, get_next_week_timetable, get_timetable_changes
    ├── people.py        # get_my_children, get_students, get_all_students, get_teachers
    ├── academics.py     # get_grades, get_homework, get_assignments
    ├── timeline.py      # get_timeline, get_notifications, get_notification_history
    ├── events.py        # get_absences, get_upcoming_events, get_student_summary
    ├── calendar.py      # get_school_days (trip/excursion/absence fusion — NO holidays)
    └── school.py        # get_classes, get_classrooms, get_subjects, get_periods, get_news, get_meals, send_message
```

### Key patterns:

- **SessionManager** (`session.py`): Manages one or more logged-in `edupage_api.Edupage` instances keyed by subdomain. Methods: `get()`, `get_all()`, `is_multi_school()`, `for_all()`, `login()`, `login_auto()`, `try_env_login()`. Supports comma-separated `EDUPAGE_SUBDOMAIN` for multi-school login.

- **Lean serializers** (`serializers.py`): Every entity type has a `lean_*()` function that extracts only useful fields (~90% smaller than `__dict__`). Also contains `serialize()` fallback, `extract_homework_fields()`, and `extract_assignment_fields()`.

- **Error handling** (`errors.py`): `@handle_errors(action)` decorator catches exceptions and returns structured JSON. `_ERROR_HINTS` maps exception class names to user-friendly messages.

- **Timeline filtering** (`filters.py`): `filter_timeline_events()` is the central filter/paginate function. Supports status, starred, event type, category, date range, with pagination. `_SYSTEM_EVENT_TYPES` hidden by default. The `by_event_date=True` flag makes the date-range filter apply to the *parsed event date* (`extract_event_date`) rather than the post timestamp — used for "event"-style items whose real date lives in the title.

- **Event-date parsing** (`dates.py`): `extract_event_date(event)` recovers the *real* event date. Edupage "event" items store the post date in `timestamp` and the real date in the title (`"Udalosť: <name> -  DD.MM.YYYY"`, 1–2 spaces before the date; also `DD.MM.YY` and `DD.MM.` → current year). Resolution order: a structured attribute (`event_date`/`date`/`start`), then a date-like key in `additional_data`, then a regex over `text`/`title` (scans for the *last* dotted token so a leading "5K Lauf" numeral isn't mistaken for a date). Pure and defensive — returns `None` if unparseable, never raises. Surfaced as `event_date` in `lean_timeline_event` output when present. As of edupage-api 0.12.x the `TimelineEvent` dataclass has **no** structured event-date field — the title regex is the only reliable source — but the structured-attr probe is kept forward-compatible.

- **Student resolution** (`resolvers.py`): `resolve_student()` does case-insensitive exact then substring match. Cross-session variants search all connected schools and auto-detect the correct one. Take `SessionManager` as first param.

- **Tool registration** (`tools/`): Each tool file has a `register(mcp, sessions)` function. Tools use closure over `sessions: SessionManager`. `tools/__init__.py` has `register_all()` that calls each sub-register.

### Tool groups (mapped to files):

| File | Tools | Notes |
|------|-------|-------|
| `tools/auth.py` | `login`, `login_auto` | Delegates to `SessionManager.login()` / `login_auto()` |
| `tools/timetable.py` | `get_timetable`, `get_next_week_timetable`, `get_timetable_changes` | Supports `student_name`, `class_name` params |
| `tools/people.py` | `get_my_children`, `get_students`, `get_all_students`, `get_teachers` | `get_my_children` is the starting point for parent accounts |
| `tools/academics.py` | `get_grades`, `get_homework`, `get_assignments` | Homework/assignments extracted from timeline via `extract_homework_fields` |
| `tools/timeline.py` | `get_timeline`, `get_notifications`, `get_notification_history` | All use `filter_timeline_events` from `filters.py` |
| `tools/events.py` | `get_absences`, `get_upcoming_events`, `get_student_summary` | `get_upcoming_events` fetches `lookback_days` (default 180) of history and filters on the *parsed event date* (from the title), not the post timestamp, so events announced months ahead surface; output includes `event_date`. Summary is all-in-one: grades + homework + exams + absences + messages |
| `tools/calendar.py` | `get_school_days` | Per-date "is the kid at school over lunch?" fusing multi-day trips (Klassenfahrt, date-range parsed from title), single-day excursions (Ausflug/Wandertag), and the student's absences. ⚠️ **Holidays are explicitly OUT of scope** — Edupage data has no reliable public/Brandenburg holiday signal, so undisrupted dates return `in_school: null` (unknown), never `true`. Caller must cross-check a holiday source / the caterer menu |
| `tools/school.py` | `get_classes`, `get_classrooms`, `get_subjects`, `get_periods`, `get_news`, `get_meals`, `send_message` | `send_message` sends real messages |

## Testing

Tests live in `tests/` covering the pure modules (`errors`, `serializers`, `filters`, `resolvers`, `session`). Uses `types.SimpleNamespace` mocks — no `edupage-api` dependency needed for tests. Any new code must include corresponding tests.

## Dependencies

- `mcp` >= 1.2.0 — MCP Python SDK (FastMCP)
- `edupage-api` >= 0.12.3 — Unofficial Edupage API client
- `pytest` (dev) — Test runner

## Auth Configuration

Set env vars `EDUPAGE_USERNAME`, `EDUPAGE_PASSWORD`, `EDUPAGE_SUBDOMAIN` before starting the server. The `.mcp.json` references these. The subdomain is the part before `.edupage.org`. For multi-school support (same credentials, different subdomains), use comma-separated values: `EDUPAGE_SUBDOMAIN=school1,school2`.
