from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError


def _canonical_args(args: dict[str, Any]) -> str:
    cleaned = {k: v for k, v in args.items() if k != "confirmation_token"}
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str)


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    import base64

    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def issue_confirmation_token(
    *,
    secret: str,
    ctx: Ctx,
    tool: str,
    args: dict[str, Any],
    ttl_seconds: int,
) -> tuple[str, str]:
    exp = int(time.time()) + ttl_seconds
    payload = {
        "tenant": ctx.tenant,
        "user_id": ctx.user_id,
        "team_id": ctx.team_id,
        "tool": tool,
        "args_hash": hashlib.sha256(_canonical_args(args).encode()).hexdigest(),
        "exp": exp,
    }
    body = _b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    sig = _b64url(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    )
    token = f"{body}.{sig}"
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
    return token, expires_at


def verify_confirmation_token(
    *,
    secret: str,
    ctx: Ctx,
    tool: str,
    args: dict[str, Any],
    token: str,
) -> None:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise AppError("validation_error", "Malformed confirmation_token") from exc

    expected_sig = _b64url(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig, expected_sig):
        raise AppError("permission_denied", "Invalid confirmation_token signature")

    try:
        payload = json.loads(_b64url_decode(body))
    except (json.JSONDecodeError, ValueError) as exc:
        raise AppError("validation_error", "Invalid confirmation_token payload") from exc

    if payload.get("tenant") != ctx.tenant or payload.get("user_id") != ctx.user_id:
        raise AppError("permission_denied", "confirmation_token ctx mismatch")
    if payload.get("team_id") != ctx.team_id:
        raise AppError("permission_denied", "confirmation_token team mismatch")
    if payload.get("tool") != tool:
        raise AppError("validation_error", "confirmation_token tool mismatch")

    args_hash = hashlib.sha256(_canonical_args(args).encode()).hexdigest()
    if payload.get("args_hash") != args_hash:
        raise AppError(
            "validation_error",
            "confirmation_token args mismatch; resubmit with the same args",
        )

    exp = int(payload.get("exp") or 0)
    if time.time() > exp:
        raise AppError("validation_error", "confirmation_token expired")


def needs_confirmation_payload(
    *,
    token: str,
    expires_at: str,
    tool: str,
    summary: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    clean_args = {k: v for k, v in args.items() if k != "confirmation_token"}
    return {
        "status": "needs_confirmation",
        "confirmation_token": token,
        "expires_at": expires_at,
        "tool": tool,
        "summary": summary,
        "args": clean_args,
    }
