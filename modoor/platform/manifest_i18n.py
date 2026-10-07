"""Normalize module.yaml top-level i18n maps."""

from __future__ import annotations

from typing import Any

# Special key: module / shell brand title. Other keys bind by entity id|key.
APP_LABEL_KEY = "app.label"


def normalize_manifest_i18n(raw: Any) -> dict[str, dict[str, str]]:
    """Keep only flat string messages: {locale: {key: text}}."""
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    for loc, pack in raw.items():
        if not isinstance(pack, dict):
            continue
        flat: dict[str, str] = {}
        for k, v in pack.items():
            if isinstance(v, str) and v.strip():
                flat[str(k)] = v.strip()
        if flat:
            out[str(loc)] = flat
    return out
