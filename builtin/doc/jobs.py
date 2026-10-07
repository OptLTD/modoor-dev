"""Doc extract job handler."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from modoor.runtime.jobs import register_handler

_REGISTERED = False


def handle_extract(session: Session, payload: dict[str, Any]) -> None:
    from builtin.doc.domain import apply_extract_job

    apply_extract_job(session, payload)


def register() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    register_handler("doc.extract", handle_extract)
    _REGISTERED = True
