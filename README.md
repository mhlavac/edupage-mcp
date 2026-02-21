# Edupage MCP Server

MCP server that connects Claude to Edupage — a school information system used across Europe. Provides access to timetables, grades, homework, messages, students, teachers, and more.

## Quick Setup

### 1. Install

```bash
cd /path/to/edupage-mcp
uv sync
```

Or if you prefer a one-liner without cloning:

```bash
uv pip install "mcp>=1.2.0" "edupage-api>=0.12.3"
```

### 2. Configure for Claude Code

The easiest way — just open the project folder and the `.mcp.json` will be picked up automatically. Set environment variables first:

```bash
export EDUPAGE_USERNAME=your_user
export EDUPAGE_PASSWORD=your_pass
export EDUPAGE_SUBDOMAIN=your_school
```

Or add the server manually:

```bash
claude mcp add edupage -- uv run --directory /path/to/edupage-mcp python -m edupage_mcp
```

With auto-login via environment variables:

```bash
claude mcp add --env EDUPAGE_USERNAME=your_user --env EDUPAGE_PASSWORD=your_pass --env EDUPAGE_SUBDOMAIN=your_school edupage -- uv run --directory /path/to/edupage-mcp python -m edupage_mcp
```

### 3. Configure for Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "edupage": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/edupage-mcp", "python", "-m", "edupage_mcp"],
      "env": {
        "EDUPAGE_USERNAME": "your_username",
        "EDUPAGE_PASSWORD": "your_password",
        "EDUPAGE_SUBDOMAIN": "your_school"
      }
    }
  }
}
```

### 4. Configure for Cowork

Use the `.mcp.json` file included in this repo — just set the environment variables.

## Authentication

Two options:

1. **Environment variables** (recommended) — set `EDUPAGE_USERNAME`, `EDUPAGE_PASSWORD`, and `EDUPAGE_SUBDOMAIN`. The server logs in automatically at startup.
2. **Manual login tool** — call the `login` or `login_auto` tool at the start of your session.

The subdomain is the part before `.edupage.org` in your school's URL (e.g. `myschool` for `https://myschool.edupage.org`).

## Available Tools

| Tool | Description |
|------|-------------|
| `login` | Log in with username, password, subdomain |
| `login_auto` | Log in via portal (auto-detect school) |
| `get_timetable` | Get timetable for a date |
| `get_next_week_timetable` | Get Mon-Fri timetable for next week |
| `get_timetable_changes` | Get substitutions / changes for a date |
| `get_grades` | Get student grades/marks |
| `get_students` | Get students in your class |
| `get_all_students` | Get all students in the school |
| `get_teachers` | Get all teachers |
| `get_classes` | Get all classes |
| `get_classrooms` | Get all classrooms |
| `get_homework` | Get homework assignments |
| `get_assignments` | Get all assignments (homework, tests, etc.) |
| `get_timeline` | Get recent timeline items |
| `get_notifications` | Get recent notifications |
| `get_notification_history` | Get notifications since a date |
| `get_news` | Get school news |
| `get_meals` | Get meal information |
| `send_message` | Send a message to users |
| `get_subjects` | Get all subjects |
| `get_periods` | Get bell schedule / periods |
| `get_my_children` | Get children linked to a parent account |
| `get_absences` | Get student absences |
| `get_upcoming_events` | Get upcoming school events |
| `get_student_summary` | All-in-one summary: grades, homework, exams, absences |

## Project Structure

```
edupage-mcp/
├── CLAUDE.md              # Developer guide
├── pyproject.toml         # Package config (uv/hatch)
├── .mcp.json              # Claude Code project config
├── .env.example           # Example environment variables
└── src/
    └── edupage_mcp/
        ├── __init__.py
        ├── __main__.py
        └── server.py      # MCP server implementation
```

## Development

Run the server directly for testing:

```bash
uv run python -m edupage_mcp
```

Test with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run python -m edupage_mcp
```

## Dependencies

- `mcp` >= 1.2.0 — Model Context Protocol Python SDK
- `edupage-api` >= 0.12.3 — Unofficial Edupage API client ([GitHub](https://github.com/EdupageAPI/edupage-api))

## Notes

- The server uses stdio transport (reads stdin, writes stdout)
- All logging goes to stderr to avoid corrupting the MCP protocol
- Session persists for the lifetime of the server process
- The `send_message` tool sends real messages — use with care
- If Edupage requests a CAPTCHA, log in via browser first then retry

## License

This project is licensed under the GPL-3.0-or-later — see the [LICENSE](LICENSE) file for details.

The `edupage-api` dependency is GPL-3.0 licensed, which requires derivative works to use a compatible license.
