"""Pulse capability package — MODULE_CONTRACT shaped manifest + artifacts."""

from __future__ import annotations

PULSE_SKILL_MD = """# Skill: Read pulse metrics

## when_to_use
When the user asks for Board-adjacent uptime / tick metrics from Pulse.

## steps
1. Call `pulse.get_metrics`.

## tools
- pulse.get_metrics

## confirmations
None.

## 禁忌 / 边界
- Read-only; do not invent metrics.
"""


def build_manifest(*, entry_url: str) -> dict:
    return {
        "id": "pulse",
        "version": "0.1.0",
        "depends": [],
        "summary": "External Pulse — Vue CSR metrics (ui-web.kind=external)",
        "exports": {
            "tools": ["pulse.get_metrics"],
            "skills": ["pulse.read_metrics"],
            "menus": [],
        },
        "ability": ["pulse.metrics.read"],
        "risk_default": "low",
        "ui-web": {
            "kind": "external",
            "label": "Pulse",
            "entry": entry_url,
            "home": entry_url,
            "recommends": ["module_switcher", "logout"],
        },
    }


def build_artifacts(*, entry_url: str) -> dict:
    base = entry_url.rstrip("/")
    return {
        "tools": [
            {
                "name": "pulse.get_metrics",
                "description": "Read Pulse uptime and tick counters.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "uptime_sec": {"type": "integer"},
                        "ticks": {"type": "integer"},
                        "modoor": {"type": "string"},
                    },
                },
                "ability": "pulse.metrics.read",
                "risk": "low",
                "idempotency": True,
                "side_effects": "read",
                "invoke_url": f"{base}/modoor/tools/pulse.get_metrics",
            }
        ],
        "skills": [
            {
                "id": "pulse.read_metrics",
                "title": "Read pulse metrics",
                "summary": "Fetch uptime/ticks from Pulse.",
                "when_to_use": "User asks for Pulse metrics.",
                "steps": ["Call pulse.get_metrics"],
                "tools": ["pulse.get_metrics"],
                "confirmations": [],
                "boundaries": "Read-only.",
                "content": PULSE_SKILL_MD,
            }
        ],
        "models": [
            {
                "name": "pulse.snapshot",
                "description": "Pulse runtime snapshot.",
                "fields": [
                    {"name": "uptime_sec", "type": "integer"},
                    {"name": "ticks", "type": "integer"},
                ],
            }
        ],
    }
