"""builtin.base — frontend entry + FastAPI registration."""

from __future__ import annotations

from fastapi import FastAPI

from modoor.web.entry import EntryContext, WebEntry
from modoor.web.kit import ShellKit
from modoor.web.mount import join_web_mount
from builtin.base.route import register as register_routes


def resolve_entry(ctx: EntryContext) -> WebEntry | None:
    # Module-local (ui-web.base); public URL = /mod + base
    base = "/base"
    home = f"{base}/users"
    public_home = join_web_mount(home)
    dist = ctx.module_root / "webui" / "dist"
    if ctx.env == "dev":
        return WebEntry(mode="url", target=f"{ctx.webui_url}{public_home}", base=base)
    if dist.is_dir():
        return WebEntry(mode="static", target=str(dist), base=base)
    return WebEntry(mode="url", target=f"{ctx.webui_url}{public_home}", base=base)


def register(app: FastAPI, kit: ShellKit) -> None:
    register_routes(app, kit)
