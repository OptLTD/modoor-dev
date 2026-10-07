#!/usr/bin/env python3
"""Manually seed demo data (not run on API/bootstrap start).

Usage:
  make seed city FORCE=1
  .venv/bin/python scripts/seed_demo.py city --force
  python3 scripts/seed_demo.py city --force   # auto-uses .venv when present
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def _ensure_project_env() -> None:
    """Prefer project venv; always put repo root on sys.path."""
    root_s = str(ROOT)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    os.environ.setdefault("PYTHONPATH", root_s)
    if not VENV_PYTHON.is_file():
        return
    # Do not compare sys.executable.resolve() — macOS venv python is a symlink
    # to the same Frameworks binary as system python3.
    venv_prefix = (ROOT / ".venv").resolve()
    try:
        if Path(sys.prefix).resolve() == venv_prefix:
            return
    except OSError:
        pass
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


_ensure_project_env()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed demo data into current tenant")
    parser.add_argument(
        "modules",
        nargs="*",
        metavar="MODULE",
        help="Modules to seed: sale, fleet, dispatch, city (default: sale fleet dispatch)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Wipe/rebuild where the seed supports force",
    )
    args = parser.parse_args(argv)
    allowed = ("sale", "fleet", "dispatch", "city")
    targets = list(args.modules) or ["sale", "fleet", "dispatch"]
    bad = [m for m in targets if m not in allowed]
    if bad:
        parser.error(f"invalid module(s): {', '.join(bad)} (choose from {', '.join(allowed)})")

    from modoor.core.db import init_db, session_scope
    from modoor.core.settings import get_settings
    from modoor.runtime.auth import resolve_ctx
    from modoor.platform.bootstrap import bootstrap

    get_settings.cache_clear()
    settings = get_settings()
    bootstrap(settings)
    init_db(settings)
    ctx = resolve_ctx(settings)
    out: dict = {"tenant": ctx.tenant, "force": bool(args.force), "results": {}}

    with session_scope() as session:
        if "sale" in targets:
            from addon.sale import domain as sale_domain

            out["results"]["sale"] = sale_domain.seed_demo_orders(
                session, ctx, force=args.force
            )
        if "fleet" in targets:
            from addon.fleet import domain as fleet_domain

            out["results"]["fleet"] = fleet_domain.seed_demo_fleet(
                session, ctx, force=args.force
            )
        if "dispatch" in targets:
            from addon.dispatch import domain as dispatch_domain

            out["results"]["dispatch"] = dispatch_domain.seed_demo_dispatch(
                session, ctx, force=args.force
            )
        if "city" in targets:
            from addon.dispatch.seed_city import seed_demo_beijing_city

            out["results"]["city"] = seed_demo_beijing_city(
                session, ctx, force=args.force
            )

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
