"""Resolve on-disk module roots: builtin/* + addon/*."""

from __future__ import annotations

from pathlib import Path

from modoor.core.settings import Settings, get_settings

# python import prefix → default relative dir under repo root
PKG_BUILTIN = "builtin"
PKG_MODULES = "addon"


def module_pkg_roots(settings: Settings | None = None) -> list[tuple[str, Path]]:
    """Ordered (import_prefix, filesystem_root) pairs."""
    settings = settings or get_settings()
    return [
        (PKG_BUILTIN, Path(settings.modoor_builtin_root)),
        (PKG_MODULES, Path(settings.modoor_modules_root)),
    ]


def find_module_dir(
    module_id: str, settings: Settings | None = None
) -> tuple[str, Path] | None:
    """Return (import_prefix, module_dir) for an on-disk module id."""
    mid = (module_id or "").strip()
    if not mid:
        return None
    for pkg, root in module_pkg_roots(settings):
        path = root / mid
        if (path / "module.yaml").is_file() or path.is_dir():
            if path.is_dir():
                return pkg, path
    return None


def module_import_prefix(module_id: str, settings: Settings | None = None) -> str:
    hit = find_module_dir(module_id, settings)
    if hit:
        return hit[0]
    return PKG_MODULES


def module_dir(module_id: str, settings: Settings | None = None) -> Path:
    hit = find_module_dir(module_id, settings)
    if hit:
        return hit[1]
    settings = settings or get_settings()
    return Path(settings.modoor_modules_root) / module_id
