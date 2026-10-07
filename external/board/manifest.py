"""Board capability package — MODULE_CONTRACT shaped manifest + artifacts."""

from __future__ import annotations

BOARD_SKILL_MD = """# Skill: Manage board notes

## when_to_use
When the user wants to list or add sticky notes on the external Board app.

## steps
1. Call `board.list_notes` to see current notes.
2. Call `board.add_note` with `{ "text": "..." }` to append a note.

## tools
- board.list_notes
- board.add_note

## confirmations
None (low risk writes).

## 禁忌 / 边界
- Do not invent notes that were not returned by tools.
- Do not call tools not listed in exports.
"""


def build_manifest(*, entry_url: str) -> dict:
    return {
        "id": "board",
        "version": "0.1.0",
        "depends": [],
        "summary": "External Board — sticky notes (ui-web.kind=external)",
        "exports": {
            "tools": ["board.list_notes", "board.add_note"],
            "skills": ["board.manage_notes"],
            "menus": [],
        },
        "ability": ["board.note.read", "board.note.write"],
        "risk_default": "low",
        "ui-web": {
            "kind": "external",
            "label": "Board",
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
                "name": "board.list_notes",
                "description": "List sticky notes on the Board.",
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": {"type": "string"}}
                    },
                },
                "ability": "board.note.read",
                "risk": "low",
                "idempotency": True,
                "side_effects": "read",
                "invoke_url": f"{base}/modoor/tools/board.list_notes",
            },
            {
                "name": "board.add_note",
                "description": "Append a sticky note on the Board.",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "ability": "board.note.write",
                "risk": "low",
                "idempotency": False,
                "side_effects": "write",
                "invoke_url": f"{base}/modoor/tools/board.add_note",
            },
        ],
        "skills": [
            {
                "id": "board.manage_notes",
                "title": "Manage board notes",
                "summary": "List and add sticky notes on Board.",
                "when_to_use": "User wants to manage Board sticky notes.",
                "steps": [
                    "Call board.list_notes",
                    "Optionally call board.add_note with text",
                ],
                "tools": ["board.list_notes", "board.add_note"],
                "confirmations": [],
                "boundaries": "Do not invent notes; only use exported tools.",
                "content": BOARD_SKILL_MD,
            }
        ],
        "models": [
            {
                "name": "board.note",
                "description": "A sticky note text item on the board.",
                "fields": [{"name": "text", "type": "string"}],
            }
        ],
    }
