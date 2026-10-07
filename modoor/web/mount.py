"""Public SPA mount root — modules declare local paths; Master prefixes at mount time."""

from __future__ import annotations

# Shell mounts every module frontend under this prefix:
#   ui-web.base=/base  →  public /mod/base
WEBUI_MOUNT_PREFIX = "/mod"


def join_web_mount(path: str) -> str:
    """Module-local path (`/base/users`) → public path (`/mod/base/users`).

    Absolute http(s) URLs and paths already under the mount are left unchanged.
    """
    raw = (path or "").strip()
    if not raw:
        return WEBUI_MOUNT_PREFIX
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if not raw.startswith("/"):
        raw = f"/{raw}"
    mount = WEBUI_MOUNT_PREFIX.rstrip("/") or ""
    if not mount:
        return raw
    if raw == mount or raw.startswith(f"{mount}/"):
        return raw
    return f"{mount}{raw}"


def strip_web_mount(path: str) -> str:
    """Public path → module-local path for matching ui-web.base."""
    raw = (path or "").strip() or "/"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if not raw.startswith("/"):
        raw = f"/{raw}"
    mount = WEBUI_MOUNT_PREFIX.rstrip("/") or ""
    if mount and (raw == mount or raw.startswith(f"{mount}/")):
        rest = raw[len(mount) :] or "/"
        return rest if rest.startswith("/") else f"/{rest}"
    return raw
