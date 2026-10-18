"""Acting role for a superuser session.

The browser keeps the choice in localStorage and sends ``X-Modoor-Role`` on API
calls. Full page loads cannot set that header, so the same value is also stored
in the ``modoor_role`` cookie.
"""

from __future__ import annotations

from typing import Any

ROLE_HEADER = "x-modoor-role"
ROLE_COOKIE = "modoor_role"


def acting_role(request: Any) -> str | None:
    header = str(request.headers.get(ROLE_HEADER) or "").strip()
    if header:
        return header
    cookie = str(request.cookies.get(ROLE_COOKIE) or "").strip()
    return cookie or None


def clear_acting_role_cookie(response: Any) -> Any:
    response.delete_cookie(ROLE_COOKIE, path="/")
    return response
