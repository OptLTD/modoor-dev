"""Platform `state` column: tinyint soft-delete / alive (PostgreSQL SMALLINT).

``STATE_ON`` = row is alive; ``STATE_OFF`` = soft-deleted.
Business enable/disable uses separate fields (e.g. fleet ``status``), not ``state``.

Sale order uses its own draft/confirmed constants below (not soft-delete).
"""

from __future__ import annotations

# Soft-delete / alive (user, team, role, fleet rows, …)
STATE_OFF = 0
STATE_ON = 1

# Sale order (business lifecycle — not soft-delete)
SALE_DRAFT = 0
SALE_CONFIRMED = 1

_SALE_LABEL = {SALE_DRAFT: "draft", SALE_CONFIRMED: "confirmed"}
_SALE_CODE = {"draft": SALE_DRAFT, "confirmed": SALE_CONFIRMED}


def is_on(state: int | None) -> bool:
    """True when the row is alive (not soft-deleted)."""
    return int(state or 0) == STATE_ON


def as_on(alive: bool) -> int:
    return STATE_ON if alive else STATE_OFF


def sale_label(state: int | None) -> str:
    return _SALE_LABEL.get(int(state or 0), "draft")


def sale_code(raw: object) -> int:
    if raw is None or raw == "":
        return SALE_DRAFT
    if isinstance(raw, bool):
        return SALE_CONFIRMED if raw else SALE_DRAFT
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return SALE_CONFIRMED if int(raw) == SALE_CONFIRMED else SALE_DRAFT
    key = str(raw).strip().lower()
    if key in _SALE_CODE:
        return _SALE_CODE[key]
    if key in ("1", "true", "yes"):
        return SALE_CONFIRMED
    return SALE_DRAFT
