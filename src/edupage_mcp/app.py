"""Edupage MCP Server — app creation and entry point."""

import logging
import sys

from mcp.server.fastmcp import FastMCP

from .session import SessionManager
from .tools import register_all

mcp = FastMCP(
    "Edupage",
    instructions=(
        "MCP server for Edupage — a school information system. "
        "Authentication is handled automatically via environment variables "
        "(EDUPAGE_USERNAME, EDUPAGE_PASSWORD, EDUPAGE_SUBDOMAIN). "
        "If not already logged in, call the 'login' tool with no arguments. "
        "Never ask the user for credentials — they must be set as env vars. "
        "Multi-school support: EDUPAGE_SUBDOMAIN can be comma-separated "
        "(e.g. 'school1,school2') to connect to multiple schools with the "
        "same credentials. When multiple schools are connected, results are "
        "merged and tagged with a 'school' field. Student-name tools "
        "(timetable, absences, summary) auto-detect the correct school. "
        "Use the 'school' parameter to filter results to a specific school. "
        "Tools expose timetables, grades, homework, messages, students, "
        "teachers, classes, and more. Use get_my_children() to find student "
        "names, then pass student_name to other tools for targeted lookups. "
        "Note: Edupage 'event' items store the announcement's post date in "
        "their timestamp, while the real event date lives in the title; "
        "get_upcoming_events parses that title date and filters on it. "
        "get_school_days gives a per-date 'is the kid at school over lunch?' "
        "view by fusing trips, excursions, and absences — but it does NOT "
        "detect public/Brandenburg holidays (out of scope); undisrupted days "
        "come back in_school=null (unknown), so cross-check a holiday source "
        "or the caterer menu before assuming a child is at school."
    ),
)

sessions = SessionManager()
register_all(mcp, sessions)


def main():
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    sessions.try_env_login()
    mcp.run(transport="stdio")
