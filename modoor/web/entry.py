"""Module frontend entry resolution — resolve_entry → url | static | template."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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


def entry_launch_href(entry: WebEntry, *, shell_base: str = "") -> str:
    """URL or path Master should open for this entry."""
    from modoor.web.mount import join_web_mount

    if entry.mode == "url":
        return entry.target
    base = join_web_mount((entry.base or "").rstrip("/") or "/")
    if entry.mode == "static":
        return base + "/" if not base.endswith("/") else base
    # template: usually already registered under base
    if base.startswith("http"):
        return base
    if shell_base and not base.startswith("http"):
        return f"{shell_base.rstrip('/')}{base}"
    return base
