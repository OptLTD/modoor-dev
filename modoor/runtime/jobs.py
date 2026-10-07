"""Postgres job queue (FOR UPDATE SKIP LOCKED)."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from modoor.core.db import Base, session_scope

log = logging.getLogger("modoor.jobs")

JobHandler = Callable[[Session, dict[str, Any]], None]
_HANDLERS: dict[str, JobHandler] = {}

STALE_AFTER = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "job_queue"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


def register_handler(kind: str, fn: JobHandler) -> None:
    _HANDLERS[kind] = fn


def enqueue(
    session: Session,
    *,
    kind: str,
    payload: dict[str, Any] | None = None,
    max_attempts: int = 3,
) -> Job:
    job = Job(
        id=str(uuid.uuid4()),
        kind=kind,
        payload=dict(payload or {}),
        status="pending",
        attempts=0,
        max_attempts=max_attempts,
        run_after=_now(),
    )
    session.add(job)
    session.flush()
    return job


def _requeue_stale(session: Session) -> None:
    cutoff = _now() - STALE_AFTER
    rows = list(
        session.scalars(
            select(Job).where(Job.status == "running", Job.locked_at.is_not(None))
        )
    )
    for job in rows:
        locked = job.locked_at
        if locked is None:
            continue
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)
        if locked < cutoff:
            job.status = "pending"
            job.locked_at = None
            job.locked_by = ""
            job.run_after = _now()
            job.updated_at = _now()


def _claim_id() -> str | None:
    with session_scope() as session:
        _requeue_stale(session)
        job = session.execute(
            select(Job)
            .where(Job.status == "pending", Job.run_after <= _now())
            .order_by(Job.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            return None
        job.status = "running"
        job.attempts = int(job.attempts or 0) + 1
        job.locked_at = _now()
        job.locked_by = str(os.getpid())
        job.updated_at = _now()
        session.flush()
        return job.id


def run_one() -> bool:
    job_id = _claim_id()
    if not job_id:
        return False
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            return True
        handler = _HANDLERS.get(job.kind)
        try:
            if handler is None:
                raise RuntimeError(f"no handler for job kind {job.kind!r}")
            handler(session, dict(job.payload or {}))
            job.status = "done"
            job.error = ""
            job.locked_at = None
            job.locked_by = ""
        except Exception as exc:  # noqa: BLE001
            log.exception("job %s (%s) failed", job.id, job.kind)
            job.error = str(exc)[:2000]
            job.locked_at = None
            job.locked_by = ""
            if job.attempts >= job.max_attempts:
                job.status = "failed"
            else:
                job.status = "pending"
                job.run_after = _now() + timedelta(seconds=2 ** max(job.attempts, 1))
        job.updated_at = _now()
    return True


def run_pending(*, limit: int = 8) -> int:
    done = 0
    for _ in range(max(int(limit), 1)):
        if not run_one():
            break
        done += 1
    return done
