"""Short-lived tickets so external apps can resolve tenant + profile."""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from modoor.core.settings import get_settings

_SALT = "modoor-external-ticket"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().modoor_session_secret, salt=_SALT)


def issue_ticket(*, user_id: int, tenant: int, max_age: int = 3600) -> str:
    return _serializer().dumps({"user_id": int(user_id), "tenant": int(tenant)})


def verify_ticket(token: str, *, max_age: int = 3600) -> dict[str, int] | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    user_id = data.get("user_id")
    tenant = data.get("tenant")
    if user_id is None or tenant is None:
        return None
    try:
        return {"user_id": int(user_id), "tenant": int(tenant)}
    except (TypeError, ValueError):
        return None
