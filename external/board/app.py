"""External demo: Board — independent app registered to Modoor (MODULE_CONTRACT)."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from fastapi import Body, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from external.board.manifest import build_artifacts, build_manifest
from external.common import (
    api_key,
    modoor_url,
    fetch_catalog,
    heartbeat_loop,
    register,
    shell_chrome,
)

SERVICE_ID = "board"
MODULE_ID = "board"
LABEL = "Board"
HOST = os.environ.get("EXTERNAL_BOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("EXTERNAL_BOARD_PORT", "8771"))
ENTRY = f"http://{HOST}:{PORT}/"

_stop = threading.Event()
_notes: list[str] = ["Welcome to Board (external)", "Register me in Modoor"]
_MANIFEST = build_manifest(entry_url=ENTRY)
_ARTIFACTS = build_artifacts(entry_url=ENTRY)


def _check_key(request: Request) -> None:
    key = request.headers.get("X-API-Key") or ""
    if key != api_key():
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="invalid api key")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    register(
        id=SERVICE_ID,
        app_name=LABEL,
        entry_url=ENTRY,
        health_url=ENTRY + "health",
        manifest=_MANIFEST,
        artifacts=_ARTIFACTS,
    )
    heartbeat_loop(
        app_id=SERVICE_ID,
        entry_url=ENTRY,
        stop=_stop,
        manifest=_MANIFEST,
        artifacts=_ARTIFACTS,
    )
    yield
    _stop.set()
    try:
        httpx.delete(
            f"{modoor_url()}/api/apps/{SERVICE_ID}",
            headers={"X-API-Key": api_key()},
            timeout=2.0,
        )
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="External Board", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_ID}


@app.get("/modoor/manifest")
def modoor_manifest():
    return {"manifest": _MANIFEST, "artifacts": _ARTIFACTS}


@app.post("/modoor/tools/board.list_notes")
def tool_list_notes(
    request: Request, body: dict[str, Any] = Body(default_factory=dict)
):
    _check_key(request)
    return {"status": "ok", "result": {"items": list(_notes)}}


@app.post("/modoor/tools/board.add_note")
def tool_add_note(
    request: Request, body: dict[str, Any] = Body(default_factory=dict)
):
    _check_key(request)
    args = body.get("arguments") or body
    text = str(args.get("text") or "").strip()
    if not text:
        return {
            "status": "error",
            "error": {"code": "validation_error", "message": "text required"},
        }
    _notes.append(text)
    return {"status": "ok", "result": {"ok": True, "items": list(_notes)}}


@app.get("/proxy/catalog")
def proxy_catalog(request: Request):
    ticket = request.headers.get("X-Modoor-Ticket") or request.query_params.get(
        "ticket"
    )
    try:
        return fetch_catalog(ticket=ticket)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"error": str(exc), "tenant": None, "profile": None, "modules": []},
            status_code=502,
        )


@app.get("/", response_class=HTMLResponse)
def home():
    items = "".join(f"<li>{n}</li>" for n in _notes)
    body = f"""
    <div class="card">
      <h1 style="margin-top:0">Board</h1>
      <p class="meta">独立应用：按 MODULE_CONTRACT 向 Modoor 注册 manifest + artifacts。</p>
      <ul>{items}</ul>
      <form method="post" action="/add" style="display:flex;gap:0.5rem;margin-top:1rem">
        <input name="text" placeholder="Add note" style="flex:1;padding:0.45rem;border:1px solid #e7e5e4" />
        <button class="primary" type="submit">Add</button>
      </form>
    </div>
    """
    return shell_chrome(LABEL, body, service_id=MODULE_ID)


@app.post("/add")
def add_note(text: str = Form("")):
    text = (text or "").strip()
    if text:
        _notes.append(text)
    return RedirectResponse("/", status_code=303)


def main() -> None:
    uvicorn.run("external.board.app:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
