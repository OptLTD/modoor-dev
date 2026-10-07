#!/usr/bin/env python3
"""Verify DATABASE_URL, create schema, bootstrap tenant/admin (no demo seed)."""

from __future__ import annotations

import sys
import time

from sqlalchemy import create_engine, text


def main() -> int:
    from modoor.platform.bootstrap import bootstrap
    from modoor.core.db import init_db
    from modoor.core.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    url = settings.database_url
    engine = create_engine(url)

    deadline = time.time() + 30
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1)
    else:
        print(f"ERROR: cannot connect to database: {url}", file=sys.stderr)
        if last_err:
            print(f"  {last_err}", file=sys.stderr)
        return 1

    init_db(settings)
    result = bootstrap(settings)
    print(f"DB schema ready: {url}")
    print(
        f"Bootstrap tenant={result['tenant']} admin={result['admin_username']} "
        f"created={result['created']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
