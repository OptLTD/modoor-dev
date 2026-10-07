"""Shared FastAPI helpers for module JSON APIs."""

from __future__ import annotations

from fastapi import HTTPException, Request

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError
from modoor.web.kit import ShellKit, get_kit
from builtin.base.domain import SystemUser


def kit() -> ShellKit:
    return get_kit()


def require_user(request: Request) -> SystemUser:
    return kit().require_user(request)


def ctx_of(user: SystemUser) -> Ctx:
    return kit().ctx(user)


def http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AppError):
        code = 404 if exc.code == "not_found" else 400
        if exc.code == "permission_denied":
            code = 403
        if exc.code == "conflict":
            code = 409
        return HTTPException(
            status_code=code,
            detail={"code": exc.code, "message": exc.message, "details": exc.details},
        )
    return HTTPException(status_code=500, detail={"code": "internal", "message": str(exc)})
