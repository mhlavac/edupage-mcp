# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

MCP server that connects Claude to Edupage — a school information system used across Europe. Single-file Python server (`src/edupage_mcp/server.py`) exposing ~25 tools via the FastMCP framework. Built on top of the `edupage-api` library.

## Development Commands

```bash
# Install dependencies
uv sync

# Run the server (stdio transport)
uv run python -m edupage_mcp

# Test with MCP Inspector
npx @modelcontextprotocol/inspector uv run python -m edupage_mcp
```

No test suite exists. No linter is configured.

## Architecture

Everything lives in `src/edupage_mcp/server.py` (~1450 lines). The module entry points (`__init__.py`, `__main__.py`) just import and call `main()`.

### Key patterns:

- **Session singleton**: `_session` holds a single `edupage_api.Edupage` instance. `_try_env_login()` attempts auto-login at startup from env vars. Tools call `_get_session()` which raises if not logged in.

- **Lean serializers**: Every entity type (lesson, grade, student, teacher, class, classroom, subject, timeline event) has a `_lean_*()` function that extracts only the useful fields from edupage-api dataclasses. This reduces response size by ~90% vs raw `__dict__` dumps. There's also a generic `_serialize()` fallback.

- **Error handling**: The `@_handle_errors(action)` decorator catches exceptions and returns structured JSON errors. `_ERROR_HINTS` maps exception class names to user-friendly messages.

- **Timeline filtering**: `_filter_timeline_events()` is the central filter/paginate function used by timeline, notification, homework, assignment, absence, and event tools. Supports filtering by status, starred, event type, category, date range, with pagination via limit/offset. System events (`_SYSTEM_EVENT_TYPES`) are hidden by default.

- **Event categories**: `_EVENT_CATEGORIES` maps human-friendly names (homework, grades, exams, messages, absences, events, news) to raw Edupage event type values. Used by the `category` parameter on timeline tools.

- **Student resolution**: `_resolve_student()` does case-insensitive exact match then substring match. `_resolve_class_for_student()` chains this with class lookup. Used by timetable, absence, and summary tools.

### Tool groups:

| Group | Tools | Notes |
|-------|-------|-------|
| Auth | `login`, `login_auto` | Env vars preferred; sets `_session` |
| Timetable | `get_timetable`, `get_next_week_timetable`, `get_timetable_changes` | Supports `student_name`, `class_name` params |
| Grades | `get_grades` | Lean format with percent, class_avg |
| People | `get_my_children`, `get_students`, `get_all_students`, `get_teachers` | `get_my_children` is the starting point for parent accounts |
| School | `get_classes`, `get_classrooms`, `get_subjects`, `get_periods` | |
| Timeline | `get_timeline`, `get_notifications`, `get_notification_history` | All use `_filter_timeline_events` |
| Homework | `get_homework`, `get_assignments` | Extract from timeline via `_extract_homework_fields` |
| Events | `get_absences`, `get_upcoming_events` | Also timeline-based |
| Summary | `get_student_summary` | All-in-one: grades + homework + exams + absences + messages |
| Other | `get_news`, `get_meals`, `send_message` | `send_message` sends real messages |

## Dependencies

- `mcp` >= 1.2.0 — MCP Python SDK (FastMCP)
- `edupage-api` >= 0.12.3 — Unofficial Edupage API client

## Auth Configuration

Set env vars `EDUPAGE_USERNAME`, `EDUPAGE_PASSWORD`, `EDUPAGE_SUBDOMAIN` before starting the server. The `.mcp.json` references these. The subdomain is the part before `.edupage.org`.
