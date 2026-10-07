"""Load model bundles: builtin|addon/<id>/models/<name>/{config,tables,inputs}.json."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from modoor.core.settings import Settings, get_settings


@dataclass
class ModelBundle:
    uukey: str
    module_id: str
    path: Path
    config: dict[str, Any]
    tables: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)

    @property
    def model(self) -> dict[str, Any]:
        return dict(self.config.get("model") or {})

    @property
    def groups(self) -> dict[str, Any]:
        return dict(self.config.get("groups") or {})

    @property
    def fields(self) -> dict[str, Any]:
        return dict(self.config.get("fields") or {})

    @property
    def clicks(self) -> dict[str, Any]:
        return dict(self.config.get("clicks") or {})


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def discover_bundles(settings: Settings | None = None) -> dict[str, ModelBundle]:
    settings = settings or get_settings()
    from modoor.platform.roots import module_pkg_roots

    out: dict[str, ModelBundle] = {}
    for _pkg, root in module_pkg_roots(settings):
        if not root.is_dir():
            continue
        for module_dir in sorted(root.iterdir()):
            if not module_dir.is_dir():
                continue
            models_dir = module_dir / "models"
            if not models_dir.is_dir():
                continue
            for model_dir in sorted(models_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                config_path = model_dir / "config.json"
                if not config_path.is_file():
                    continue
                config = _read_json(config_path)
                model_meta = config.get("model") or {}
                uukey = str(model_meta.get("uukey") or "").strip()
                if not uukey:
                    continue
                out[uukey] = ModelBundle(
                    uukey=uukey,
                    module_id=module_dir.name,
                    path=model_dir,
                    config=config,
                    tables=_read_json(model_dir / "tables.json"),
                    inputs=_read_json(model_dir / "inputs.json"),
                )
    _mount_login_views(out)
    return out


def _mount_login_views(bundles: dict[str, ModelBundle]) -> None:
    """档案 extra.login 是用户列表页签名。登录身份都挂在 base.user 上。"""
    user = bundles.get("base.user")
    if user is None:
        return
    profiles: list[tuple[str, str]] = []
    for uukey, bundle in bundles.items():
        if uukey == "base.user":
            continue
        label = str((bundle.model.get("extra") or {}).get("login") or "").strip()
        if label:
            profiles.append((uukey, label))
    profiles.sort(key=lambda item: (0 if item[0].startswith("system.") else 1, item[0]))
    tables = dict(user.tables)
    default = tables.get("default") or {}
    for uukey, label in profiles:
        tables[uukey] = {
            "uukey": uukey,
            "title": label,
            "fields": list(default.get("fields") or []),
            "sticky": list(default.get("sticky") or []),
            "clicks": list(default.get("clicks") or []),
            "filters": list(default.get("filters") or []),
            "query": {"basic.model": uukey},
            "extra": {"login": True},
        }
    user.tables = tables


def login_tabs(model: str) -> list[dict[str, str]]:
    """用户列表页签。没有登录身份声明时返回空，页面保持原来的一张表。"""
    bundle = get_bundle(model)
    tabs = [
        {"using": key, "label": str(view.get("title") or key)}
        for key, view in bundle.tables.items()
        if (view.get("extra") or {}).get("login")
    ]
    if not tabs:
        return []
    return [{"using": "default", "label": "全部用户"}, *tabs]


@lru_cache
def bundled_models() -> dict[str, ModelBundle]:
    return discover_bundles()


def clear_bundle_cache() -> None:
    bundled_models.cache_clear()


def get_bundle(model: str) -> ModelBundle:
    bundles = bundled_models()
    if model not in bundles:
        # allow cache stale after new files in tests
        clear_bundle_cache()
        bundles = bundled_models()
    if model not in bundles:
        raise KeyError(f"unknown model: {model}")
    return bundles[model]


def load_sample_oplogs(model: str, code: str, limit: int = 200) -> list[dict[str, Any]]:
    """Draft audit rows from models/<entity>/oplog.json (if present)."""
    key = str(code or "").strip()
    if not key:
        return []
    try:
        bundle = get_bundle(model)
    except Exception:  # noqa: BLE001 — unknown model
        return []
    path = Path(bundle.path) / "oplog.json"
    if not path.is_file():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    records = raw.get("records") if isinstance(raw, dict) else raw
    if not isinstance(records, list):
        return []
    rows = [
        dict(item)
        for item in records
        if isinstance(item, dict) and str(item.get("code") or "").strip() == key
    ]
    rows.sort(key=lambda r: str(r.get("utime") or ""), reverse=True)
    cap = max(1, min(int(limit or 200), 500))
    return rows[:cap]
