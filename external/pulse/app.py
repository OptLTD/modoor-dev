"""External demo: Pulse — Vue CSR + MODULE_CONTRACT registration."""

from __future__ import annotations

import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from external.common import api_key, modoor_url, fetch_catalog, heartbeat_loop, register
from external.pulse.manifest import build_artifacts, build_manifest

SERVICE_ID = "pulse"
MODULE_ID = "pulse"
LABEL = "Pulse"
HOST = os.environ.get("EXTERNAL_PULSE_HOST", "127.0.0.1")
PORT = int(os.environ.get("EXTERNAL_PULSE_PORT", "8772"))
ENTRY = f"http://{HOST}:{PORT}/"
STATIC_DIR = Path(__file__).resolve().parent / "static"

_stop = threading.Event()
_started = time.time()
_ticks = 0
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


app = FastAPI(title="External Pulse", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_ID, "ui": "vue-csr"}


@app.get("/modoor/manifest")
def modoor_manifest():
    return {"manifest": _MANIFEST, "artifacts": _ARTIFACTS}


@app.post("/modoor/tools/pulse.get_metrics")
def tool_get_metrics(
    request: Request, body: dict[str, Any] = Body(default_factory=dict)
):
    _check_key(request)
    global _ticks
    _ticks += 1
    return {
        "status": "ok",
        "result": {
            "uptime_sec": int(time.time() - _started),
            "ticks": _ticks,
            "modoor": modoor_url(),
        },
    }


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


@app.get("/api/pulse")
def pulse_data():
    global _ticks
    _ticks += 1
    return {
        "uptime_sec": int(time.time() - _started),
        "ticks": _ticks,
        "modoor": modoor_url(),
    }


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


def main() -> None:
    uvicorn.run("external.pulse.app:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
