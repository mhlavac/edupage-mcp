"""Authentication tools — login, login_auto."""

from mcp.server.fastmcp import FastMCP

from ..session import SessionManager


def register(mcp: FastMCP, sessions: SessionManager) -> None:
    @mcp.tool()
    def login(username: str = "", password: str = "", subdomain: str = "") -> str:
        """
        Log in to Edupage.

        Args:
            username: Your Edupage username
            password: Your Edupage password
            subdomain: Your school's Edupage subdomain (e.g. 'myschool' for myschool.edupage.org)

        Returns:
            Success or error message
        """
        return sessions.login(username, password, subdomain)

    @mcp.tool()
    def login_auto(username: str = "", password: str = "") -> str:
        """
        Log in to Edupage via the portal (auto-detect school).

        Args:
            username: Your Edupage username / email
            password: Your Edupage password

        Returns:
            Success or error message
        """
        return sessions.login_auto(username, password)
