"""Mount module frontends under /mod/<module> — Vite proxy in dev, dist static otherwise."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Iterable

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response as StarletteResponse
from starlette.types import Scope

from modoor.core.settings import get_settings
from modoor.web.mount import WEBUI_MOUNT_PREFIX, join_web_mount
from modoor.web.nav import get_ui_catalog

logger = logging.getLogger(__name__)

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def parse_webui_proxies(raw: str) -> list[tuple[str, str]]:
    """Parse `base=http://127.0.0.1:5175,wiki=…` → [(/mod/base, url), ...]."""
    out: list[tuple[str, str]] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        mid, url = part.split("=", 1)
        mid = mid.strip().strip("/")
        url = url.strip().rstrip("/")
        if not mid or not url:
            continue
        # Allow either "base" or "mod/base" in env.
        if mid.startswith("mod/"):
            prefix = f"/{mid}"
        else:
            prefix = f"{WEBUI_MOUNT_PREFIX}/{mid}"
        out.append((prefix, url))
    return out


def register_frontends(app: FastAPI) -> list[str]:
    """Dev proxy wins per prefix; remaining modules with webui/dist are served static."""
    settings = get_settings()
    proxies = parse_webui_proxies(settings.modoor_webui_proxies)
    skip = {prefix for prefix, _ in proxies}
    registered = _register_proxies(app, proxies)
    registered.extend(_register_statics(app, skip_prefixes=skip))
    return registered


def _filter_request_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {k: v for k, v in headers if k.lower() not in _HOP_BY_HOP}


def _register_proxies(app: FastAPI, proxies: list[tuple[str, str]]) -> list[str]:
    registered: list[str] = []
    for prefix, upstream in proxies:
        _mount_proxy(app, prefix, upstream)
        registered.append(f"{prefix} → {upstream}")
        logger.info("frontend proxy %s → %s", prefix, upstream)
    return registered


def _mount_proxy(app: FastAPI, prefix: str, upstream: str) -> None:
    prefix = prefix.rstrip("/") or "/"
    upstream_host = httpx.URL(upstream).netloc

    async def proxy_http(request: Request, full_path: str = "") -> Response:
        # Vite base is "/mod/wiki/" (trailing slash). Empty path must keep it.
        if not full_path:
            if not str(request.url.path).endswith("/"):
                q = f"?{request.url.query}" if request.url.query else ""
                return RedirectResponse(url=f"{prefix}/{q}", status_code=307)
            path = f"{prefix}/"
        else:
            path = f"{prefix}/{full_path}"
        url = f"{upstream}{path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"

        body = await request.body()
        headers = _filter_request_headers(request.headers.items())
        headers["host"] = upstream_host

        try:
            # trust_env=False: local Vite must not go through HTTP(S)_PROXY / ALL_PROXY.
            async with httpx.AsyncClient(
                follow_redirects=False, timeout=60.0, trust_env=False
            ) as client:
                upstream_res = await client.request(
                    request.method,
                    url,
                    headers=headers,
                    content=body,
                )
        except (httpx.ConnectError, httpx.ProxyError, ImportError, OSError) as exc:
            return Response(
                content=f"frontend upstream unavailable: {upstream}\n{exc}",
                status_code=502,
                media_type="text/plain",
            )

        out_headers = {
            k: v
            for k, v in upstream_res.headers.items()
            if k.lower() not in _HOP_BY_HOP and k.lower() != "content-encoding"
        }
        return Response(
            content=upstream_res.content,
            status_code=upstream_res.status_code,
            headers=out_headers,
            media_type=upstream_res.headers.get("content-type"),
        )

    app.add_api_route(
        f"{prefix}/{{full_path:path}}",
        proxy_http,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    app.add_api_route(
        prefix,
        proxy_http,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )

    async def proxy_ws(websocket: WebSocket, full_path: str = "") -> None:
        path = f"{prefix}/" if not full_path else f"{prefix}/{full_path}"
        query = websocket.scope.get("query_string", b"").decode()
        ws_base = upstream.replace("http://", "ws://").replace("https://", "wss://")
        url = f"{ws_base}{path}"
        if query:
            url = f"{url}?{query}"

        await websocket.accept()
        try:
            import websockets
        except ImportError:
            await websocket.close(code=1011)
            return

        try:
            async with websockets.connect(url) as upstream_ws:

                async def client_to_upstream() -> None:
                    try:
                        while True:
                            msg = await websocket.receive()
                            if msg["type"] == "websocket.disconnect":
                                break
                            if msg.get("text") is not None:
                                await upstream_ws.send(msg["text"])
                            elif msg.get("bytes") is not None:
                                await upstream_ws.send(msg["bytes"])
                    except WebSocketDisconnect:
                        pass

                async def upstream_to_client() -> None:
                    try:
                        async for message in upstream_ws:
                            if isinstance(message, bytes):
                                await websocket.send_bytes(message)
                            else:
                                await websocket.send_text(message)
                    except Exception:
                        pass

                _done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(client_to_upstream()),
                        asyncio.create_task(upstream_to_client()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
        except Exception:
            logger.exception("websocket proxy failed %s", url)
            try:
                await websocket.close(code=1011)
            except Exception:
                pass

    app.add_api_websocket_route(f"{prefix}/{{full_path:path}}", proxy_ws)
    app.add_api_websocket_route(prefix, proxy_ws)


class SPAStaticFiles(StaticFiles):
    """Serve index.html for client-side routes under the mount."""

    async def get_response(self, path: str, scope: Scope) -> StarletteResponse:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def _module_ids_from_env(raw: str) -> list[str] | None:
    """MODOOR_WEBUI_STATIC_MODULES=base,wiki → filter; empty → all with dist."""
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    return parts or None


def _register_statics(
    app: FastAPI,
    *,
    skip_prefixes: set[str],
) -> list[str]:
    settings = get_settings()
    from modoor.platform.roots import module_dir

    catalog = get_ui_catalog()
    wanted = _module_ids_from_env(
        getattr(settings, "modoor_webui_static_modules", "") or ""
    )
    registered: list[str] = []

    for mid, meta in catalog.items():
        if wanted is not None and mid not in wanted:
            continue
        base = (meta.get("base") or f"/{mid}").rstrip("/") or f"/{mid}"
        public = join_web_mount(base).rstrip("/")
        if public in skip_prefixes or any(public.startswith(f"{p}/") for p in skip_prefixes):
            continue
        dist = module_dir(mid, settings) / "webui" / "dist"
        if not dist.is_dir() or not (dist / "index.html").is_file():
            continue
        app.mount(
            public,
            SPAStaticFiles(directory=str(dist), html=True),
            name=f"webui-static-{mid}",
        )
        registered.append(f"{public} → {dist}")
        logger.info("frontend static %s → %s", public, dist)

    if registered:
        logger.info("frontend static mount root %s (%d apps)", WEBUI_MOUNT_PREFIX, len(registered))
    return registered
