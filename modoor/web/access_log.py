"""Drop dev-frontend noise from the access log.

Vite source files are proxied through this process, so each one prints twice:
uvicorn's access line, and httpx's ``HTTP Request:`` line. Successful module
assets stay quiet. API calls and failures still print.
"""

from __future__ import annotations

import logging
from urllib.parse import unquote

_STATIC_MARKERS = (
    "/@fs/",
    "/@vite/",
    "/@id/",
    "/@react-refresh",
    "/node_modules/",
    "/__vite",
)
_STATIC_SUFFIXES = (
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".js",
    ".mjs",
    ".cjs",
    ".css",
    ".vue",
    ".scss",
    ".map",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
)


def request_path(target: object) -> str:
    text = unquote(str(target or ""))
    if "://" in text:
        rest = text.split("://", 1)[1]
        slash = rest.find("/")
        text = rest[slash:] if slash >= 0 else "/"
    return text.split("?", 1)[0]


def is_browser_probe(path: str) -> bool:
    return path.startswith("/.well-known/") or path in {"/favicon.ico", "/logo.png"}


def is_quiet_static_access(method: object, path: object, status: object) -> bool:
    raw = request_path(path)
    if is_browser_probe(raw):
        return True
    try:
        code = int(status)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if code >= 400:
        return False
    if str(method or "").upper() not in {"GET", "HEAD"}:
        return False
    if any(marker in raw for marker in _STATIC_MARKERS):
        return True
    return raw.startswith("/mod/") and raw.endswith(_STATIC_SUFFIXES)


def is_quiet_proxy_request(method: object, url: object, status: object) -> bool:
    """httpx log of a successful hop to the dev frontend."""
    try:
        code = int(status)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if code >= 400:
        return False
    if str(method or "").upper() not in {"GET", "HEAD"}:
        return False
    return request_path(url).startswith("/mod/")


class QuietStaticAccess(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        return not is_quiet_static_access(args[1], args[2], args[4])


class QuietProxyRequest(logging.Filter):
    """httpx: ``HTTP Request: METHOD URL "HTTP/1.1 STATUS REASON"``."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 4:
            return True
        return not is_quiet_proxy_request(args[0], args[1], args[3])


def _install(logger: logging.Logger, filt: logging.Filter) -> None:
    if any(type(item) is type(filt) for item in logger.filters):
        return
    logger.addFilter(filt)


def log_filter() -> None:
    _install(logging.getLogger("uvicorn.access"), QuietStaticAccess())
    _install(logging.getLogger("httpx"), QuietProxyRequest())
