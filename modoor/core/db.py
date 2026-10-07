from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from modoor.core.settings import Settings, get_settings
from modoor.core.schema import (
    ensure_partial_unique_index as _ensure_partial_unique_index,
    table_exists as _table_exists,
)

log = logging.getLogger("modoor.db")

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

# 超过该阈值（毫秒）记为慢查询；可用环境变量 MODOOR_SLOW_QUERY_MS 覆盖
_DEFAULT_SLOW_QUERY_MS = 100


def _slow_query_ms(settings: Settings | None = None) -> float:
    s = settings or get_settings()
    raw = getattr(s, "slow_query_ms", None)
    try:
        return float(raw if raw is not None else _DEFAULT_SLOW_QUERY_MS)
    except (TypeError, ValueError):
        return float(_DEFAULT_SLOW_QUERY_MS)


def _install_slow_query_logging(engine: Engine, *, threshold_ms: float) -> None:
    """SQLAlchemy cursor 事件：执行超过 threshold_ms 写 warning 日志。"""

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        conn.info["modoor_query_start"] = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        start = conn.info.pop("modoor_query_start", None)
        if start is None:
            return
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if elapsed_ms < threshold_ms:
            return
        sql = " ".join(str(statement or "").split())
        if len(sql) > 800:
            sql = sql[:800] + "…"
        params = parameters
        if params is not None:
            try:
                rendered = repr(params)
            except Exception:  # noqa: BLE001
                rendered = "<unrepr-params>"
            if len(rendered) > 400:
                rendered = rendered[:400] + "…"
        else:
            rendered = ""
        log.warning(
            "slow_query %.1fms%s | %s%s",
            elapsed_ms,
            " (executemany)" if executemany else "",
            sql,
            f" | params={rendered}" if rendered else "",
        )


class Base(DeclarativeBase):
    pass


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db(settings: Settings | None = None, *, recreate: bool = False) -> Engine:
    global _engine, _SessionLocal
    reset_engine()
    settings = settings or get_settings()
    engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
    _install_slow_query_logging(engine, threshold_ms=_slow_query_ms(settings))

    # Platform tables + enabled module domains only (lazy schema).
    from modoor.platform import module_state as _module_state  # noqa: F401
    from modoor.platform import services as _services  # noqa: F401
    from modoor.platform.loader import load_module_domains, modules_to_load, register_module_migrate
    from modoor.runtime import audit as _audit  # noqa: F401
    from modoor.runtime import jobs as _jobs  # noqa: F401

    wanted = modules_to_load(settings)
    load_module_domains(settings, module_ids=wanted)

    if recreate:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        register_module_migrate(conn, settings, module_ids=wanted)
        _ensure_runtime_indexes(conn)
    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine


@contextmanager
def session_scope() -> Iterator[Session]:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_runtime_indexes(conn) -> None:
    """Partial unique indexes not expressed on ORM models."""
    from sqlalchemy import text

    # registry_service → app_registry (rename if upgrading in place)
    if _table_exists(conn, "registry_service") and not _table_exists(conn, "app_registry"):
        conn.execute(text('ALTER TABLE registry_service RENAME TO app_registry'))
    # legacy tenant app catalog — superseded by app_install + app_registry
    if _table_exists(conn, "base_app"):
        conn.execute(text("DROP TABLE IF EXISTS base_app CASCADE"))

    if _table_exists(conn, "base_token"):
        _ensure_partial_unique_index(
            conn,
            "uq_base_token_value",
            "base_token",
            "token",
            "token IS NOT NULL AND btrim(token) <> ''",
        )
    if _table_exists(conn, "base_user"):
        _ensure_partial_unique_index(
            conn,
            "uq_base_user_tenant_email",
            "base_user",
            "tenant, lower(btrim(email))",
            "email IS NOT NULL AND btrim(email) <> ''",
        )
        _ensure_partial_unique_index(
            conn,
            "uq_base_user_tenant_phone",
            "base_user",
            "tenant, lower(btrim(phone))",
            "phone IS NOT NULL AND btrim(phone) <> ''",
        )
