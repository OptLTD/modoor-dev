"""Job worker: poll Postgres queue. Used in-process (API) or `make worker`."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from modoor.core.settings import get_settings

log = logging.getLogger("modoor.worker")

_stop = threading.Event()
_thread: threading.Thread | None = None
_last_enqueue: dict[str, float] = {}
_last_daily: dict[str, str] = {}


def daily_job_due(now: datetime, clock: str, last_day: str | None) -> bool:
    """True once on each local calendar day at or after ``HH:MM``."""
    hour_s, minute_s = str(clock).split(":", 1)
    if (now.hour, now.minute) < (int(hour_s), int(minute_s)):
        return False
    return last_day != now.date().isoformat()


def _ensure_handlers() -> None:
    from modoor.platform.loader import register_module_jobs

    register_module_jobs()


def _enqueue_due_scheduled() -> None:
    from modoor.core.db import session_scope
    from modoor.platform.loader import scheduled_jobs_from_manifests
    from modoor.runtime import jobs as jobs_mod
    from modoor.runtime.jobs import enqueue

    from modoor.engine.query import BUSINESS_TZ

    now = time.monotonic()
    wall = datetime.now(BUSINESS_TZ)
    today = wall.date().isoformat()
    for job in scheduled_jobs_from_manifests():
        kind = str(job.get("kind") or "")
        if not kind or kind not in jobs_mod._HANDLERS:
            continue
        daily = str(job.get("daily") or "")
        if daily:
            if not daily_job_due(wall, daily, _last_daily.get(kind)):
                continue
            try:
                with session_scope() as session:
                    enqueue(session, kind=kind, payload={})
            except Exception:  # noqa: BLE001
                log.debug("scheduled enqueue skipped: %s", kind, exc_info=True)
                continue
            _last_daily[kind] = today
            continue
        every = float(job.get("every") or 0)
        if every <= 0:
            continue
        last = _last_enqueue.get(kind, 0.0)
        if now - last < every:
            continue
        _last_enqueue[kind] = now
        try:
            with session_scope() as session:
                enqueue(session, kind=kind, payload={})
        except Exception:  # noqa: BLE001
            log.debug("scheduled enqueue skipped: %s", kind, exc_info=True)


def run_forever(*, poll_seconds: float | None = None) -> None:
    from modoor.runtime.jobs import run_pending

    _ensure_handlers()
    settings = get_settings()
    interval = float(
        poll_seconds if poll_seconds is not None else settings.modoor_jobs_poll_seconds
    )
    interval = max(interval, 0.2)
    log.info("job worker polling every %.2fs", interval)
    while not _stop.is_set():
        try:
            _enqueue_due_scheduled()
            n = run_pending(limit=8)
            if n:
                continue
        except Exception:  # noqa: BLE001
            log.exception("job worker loop error")
        _stop.wait(interval)


def start_inprocess() -> None:
    global _thread
    settings = get_settings()
    if not settings.modoor_jobs_inprocess:
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _ensure_handlers()
    _thread = threading.Thread(target=run_forever, name="modoor-jobs", daemon=True)
    _thread.start()
    log.info("in-process job worker started")


def stop_inprocess() -> None:
    global _thread
    _stop.set()
    t = _thread
    _thread = None
    if t is not None:
        t.join(timeout=3)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    from modoor.platform.bootstrap import bootstrap
    from modoor.core.db import init_db

    get_settings.cache_clear()
    init_db()
    bootstrap()
    _stop.clear()
    try:
        run_forever()
    except KeyboardInterrupt:
        _stop.set()


if __name__ == "__main__":
    main()
