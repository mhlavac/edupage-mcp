"""Tool registration for Edupage MCP server."""

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager
from . import academics, auth, calendar, events, people, school, timeline, timetable


def register_all(mcp: FastMCP, sessions: SessionManager) -> None:
    """Register all MCP tools on the given server instance."""
    auth.register(mcp, sessions)
    timetable.register(mcp, sessions)
    people.register(mcp, sessions)
    academics.register(mcp, sessions)
    timeline.register(mcp, sessions)
    events.register(mcp, sessions)
    school.register(mcp, sessions)
    calendar.register(mcp, sessions)
