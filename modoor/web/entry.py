"""Module frontend entry resolution — resolve_entry → url | static | template."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from modoor.core.settings import Settings, get_settings

logger = logging.getLogger(__name__)

EntryMode = Literal["url", "static", "template"]


@dataclass(frozen=True)
class WebEntry:
    mode: EntryMode
    target: str
    base: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "target": self.target,
            "base": self.base,
        }


@dataclass(frozen=True)
class EntryContext:
    module_id: str
    module_root: Path
    env: str  # "dev" | "prod"
    settings: Settings
    tenant_id: str | None = None

    @property
    def webui_url(self) -> str:
        return (self.settings.modoor_webui_url or "").rstrip("/")

    @property
    def module_webui_url(self) -> str | None:
        """Dev/prod URL for this module's own frontend, if configured."""
        raw = self.settings.modoor_module_urls or ""
        for part in raw.split(","):
            part = part.strip()
            if not part or "=" not in part:
                continue
            mid, url = part.split("=", 1)
            if mid.strip() == self.module_id:
                return url.strip().rstrip("/")
        return None


def _detect_env(settings: Settings) -> str:
    # Prefer explicit flag later; for now: non-default webui host ⇒ likely dev proxy
    url = (settings.modoor_webui_url or "").lower()
    if "127.0.0.1" in url or "localhost" in url:
        return "dev"
    return "prod"


def entry_context(
    module_id: str,
    *,
    settings: Settings | None = None,
    tenant_id: str | None = None,
) -> EntryContext:
    settings = settings or get_settings()
    from modoor.platform.roots import module_dir

    root = module_dir(module_id, settings)
    return EntryContext(
        module_id=module_id,
        module_root=root,
        env=_detect_env(settings),
        settings=settings,
        tenant_id=tenant_id or settings.modoor_tenant,
    )


def load_resolve_entry(module_id: str):
    """Import <pkg>.<id>.webui.resolve_entry if present."""
    from modoor.platform.roots import module_import_prefix

    pkg = module_import_prefix(module_id)
    for dotted in (f"{pkg}.{module_id}.webui",):
        try:
            mod = importlib.import_module(dotted)
        except ModuleNotFoundError:
            continue
        fn = getattr(mod, "resolve_entry", None)
        if callable(fn):
            return fn
    return None


def call_resolve_entry(
    module_id: str,
    *,
    settings: Settings | None = None,
    tenant_id: str | None = None,
    ctx: EntryContext | None = None,
) -> WebEntry | None:
    """Run module resolve_entry; return None if missing or returns None."""
    fn = load_resolve_entry(module_id)
    if fn is None:
        return None
    context = ctx or entry_context(module_id, settings=settings, tenant_id=tenant_id)
    try:
        result = fn(context)
    except Exception:
        logger.exception("resolve_entry failed for module %s", module_id)
        return None
    if result is None:
        return None
    if isinstance(result, WebEntry):
        return result
    if isinstance(result, dict):
        mode = result.get("mode")
        target = result.get("target")
        if mode not in ("url", "static", "template") or not target:
            logger.warning("invalid WebEntry dict from %s: %s", module_id, result)
            return None
        return WebEntry(
            mode=mode,
            target=str(target),
            base=result.get("base"),
        )
    logger.warning("resolve_entry for %s returned unsupported type %s", module_id, type(result))
    return None


def _origin_port(parsed, scheme: str) -> int:
    if parsed.port is not None:
        return parsed.port
    return 443 if scheme == "https" else 80


def _same_origin(left, right) -> bool:
    return (
        (left.hostname or "").lower() == (right.hostname or "").lower()
        and _origin_port(left, left.scheme or "http") == _origin_port(right, right.scheme or "http")
    )


def _path_on_gate(target: str) -> str:
    """Public gate is prefixed. An empty or intranet gate stays a path."""
    raw = (target or "").strip()
    from modoor.core.settings import public_module_gate

    settings = get_settings()
    public = public_module_gate(settings.modoor_webui_url)
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        if public and _same_origin(parsed, urlparse(public)):
            return f"{public}{path}"
        listen = urlparse(f"http://{settings.modoor_web_host}:{settings.modoor_web_port}")
        gate = urlparse((settings.modoor_webui_url or "").strip() or "http://127.0.0.1:8765")
        if _same_origin(parsed, listen) or _same_origin(parsed, gate):
            return f"{public}{path}" if public else path
        return raw
    if not public:
        return raw
    if raw and not raw.startswith("/"):
        raw = f"/{raw}"
    return f"{public}{raw or '/'}"


def entry_launch_href(entry: WebEntry, *, shell_base: str = "") -> str:
    """URL or path Master should open for this entry."""
    from modoor.web.mount import join_web_mount

    if entry.mode == "url":
        return _path_on_gate(entry.target)
    base = join_web_mount((entry.base or "").rstrip("/") or "/")
    if entry.mode == "static":
        href = base + "/" if not base.endswith("/") else base
        return _path_on_gate(href)
    # template: usually already registered under base
    if base.startswith("http"):
        return _path_on_gate(base)
    if shell_base and not base.startswith("http"):
        return _path_on_gate(f"{shell_base.rstrip('/')}{base}")
    return base
