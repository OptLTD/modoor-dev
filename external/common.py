"""Shared helpers for external demo apps talking to Modoor registry."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx

DEFAULT_MODOOR_URL = "http://127.0.0.1:8765"


def modoor_url() -> str:
    return os.environ.get("MODOOR_URL", DEFAULT_MODOOR_URL).rstrip("/")


def api_key() -> str:
    return os.environ.get("MODOOR_API_KEY", "dev-key-change-me")


def register(
    *,
    id: str,
    entry_url: str,
    app_name: str = "",
    health_url: str | None = None,
    module_id: str | None = None,
    manifest: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    retries: int = 30,
    delay: float = 1.0,
) -> dict[str, Any]:
    """Register with Modoor using MODULE_CONTRACT manifest + artifacts."""
    app_id = (id or "").strip()
    payload: dict[str, Any] = {
        "id": app_id,
        "entry_url": entry_url,
        "app_name": app_name or app_id,
        "health_url": health_url,
    }
    if module_id and module_id.strip() and module_id.strip() != app_id:
        payload["module_id"] = module_id.strip()
    if manifest:
        payload["manifest"] = manifest
    if artifacts:
        payload["artifacts"] = artifacts
    headers = {"X-API-Key": api_key()}
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            r = httpx.post(
                f"{modoor_url()}/api/apps",
                json=payload,
                headers=headers,
                timeout=3.0,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(delay)
    raise RuntimeError(f"register failed after retries: {last_err}")


def heartbeat_loop(
    *,
    app_id: str,
    entry_url: str,
    interval: float = 15.0,
    stop: threading.Event | None = None,
    manifest: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> None:
    stop = stop or threading.Event()
    headers = {"X-API-Key": api_key()}
    aid = (app_id or "").strip()

    def _run() -> None:
        while not stop.is_set():
            try:
                body: dict[str, Any] = {"entry_url": entry_url}
                if manifest:
                    body["manifest"] = manifest
                if artifacts:
                    body["artifacts"] = artifacts
                httpx.post(
                    f"{modoor_url()}/api/apps/{aid}/heartbeat",
                    json=body,
                    headers=headers,
                    timeout=3.0,
                )
            except Exception:  # noqa: BLE001
                pass
            stop.wait(interval)

    t = threading.Thread(target=_run, name=f"hb-{aid}", daemon=True)
    t.start()


def fetch_catalog(*, ticket: str | None = None) -> dict[str, Any]:
    headers = {}
    if ticket:
        headers["X-Modoor-Ticket"] = ticket
    r = httpx.get(
        f"{modoor_url()}/api/apps/catalog",
        headers=headers,
        timeout=3.0,
    )
    r.raise_for_status()
    return r.json()


def shell_chrome(app_title: str, body_html: str, *, service_id: str) -> str:
    """Minimal independent UI with recommended module switcher + logout."""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{app_title}</title>
  <style>
    :root {{ --ink:#1c1917; --muted:#78716c; --line:#e7e5e4; --accent:#0f766e; --bg:#f4f7f6; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:"IBM Plex Sans", "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); }}
    header {{
      display:flex; align-items:center; justify-content:space-between; gap:1rem;
      padding:0.75rem 1.25rem; background:#fff; border-bottom:1px solid var(--line);
    }}
    .brand {{ font-weight:700; }}
    .hint {{ color:var(--muted); font-size:0.8rem; margin-left:0.5rem; }}
    .actions {{ display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; }}
    select, a.btn, button {{
      font:inherit; padding:0.4rem 0.65rem; border:1px solid var(--line); background:#fff; color:var(--ink); cursor:pointer;
    }}
    a.btn, button.primary {{ background:var(--accent); color:#fff; border:none; text-decoration:none; }}
    main {{ max-width:880px; margin:1.5rem auto; padding:0 1rem; }}
    .card {{ background:#fff; border:1px solid var(--line); padding:1.25rem; }}
    .meta {{ color:var(--muted); font-size:0.9rem; }}
    .status {{ font-size:0.8rem; color:var(--muted); }}
    .status.ok {{ color:var(--accent); }}
    .status.bad {{ color:#b91c1c; }}
    .who {{ font-size:0.85rem; color:var(--muted); }}
  </style>
</head>
<body>
  <header>
    <div>
      <span class="brand">{app_title}</span>
      <span class="hint">external · via Modoor registry</span>
    </div>
    <div class="actions">
      <span class="who" id="who">…</span>
      <label class="meta">Module
        <select id="module-switch" aria-label="Switch module"></select>
      </label>
      <a class="btn" id="logout-link" href="#">Log out</a>
    </div>
  </header>
  <main>
    <p class="status" id="reg-status">Connecting to Modoor…</p>
    {body_html}
  </main>
  <script>
    (function () {{
      var selfId = {service_id!r};
      var KEY = "modoor_ticket";
      var params = new URLSearchParams(location.search);
      if (params.get("modoor_ticket")) {{
        sessionStorage.setItem(KEY, params.get("modoor_ticket"));
        params.delete("modoor_ticket");
        var q = params.toString();
        history.replaceState(null, "", location.pathname + (q ? "?" + q : "") + location.hash);
      }}
      function ticket() {{ return sessionStorage.getItem(KEY) || ""; }}
      async function refresh() {{
        var st = document.getElementById("reg-status");
        var sel = document.getElementById("module-switch");
        var logout = document.getElementById("logout-link");
        var who = document.getElementById("who");
        try {{
          var res = await fetch("/proxy/catalog", {{
            headers: ticket() ? {{ "X-Modoor-Ticket": ticket() }} : {{}}
          }});
          if (!res.ok) throw new Error("catalog " + res.status);
          var data = await res.json();
          var t = data.tenant || {{}};
          var p = data.profile;
          st.textContent = "Registry ok · tenant=" + (t.id || t.name || "?");
          st.className = "status ok";
          who.textContent = p
            ? ((p.realname || p.username) + " · " + (t.id || ""))
            : ("tenant " + (t.id || "?") + " · no profile");
          logout.href = data.logout_url || "#";
          sel.innerHTML = "";
          (data.modules || []).forEach(function (m) {{
            var opt = document.createElement("option");
            opt.value = m.href;
            opt.textContent = m.label + (m.online === false ? " (offline)" : "");
            if (m.id === selfId) opt.selected = true;
            sel.appendChild(opt);
          }});
        }} catch (e) {{
          st.textContent = "Registry unavailable — is Modoor running?";
          st.className = "status bad";
        }}
      }}
      document.getElementById("module-switch").addEventListener("change", function (e) {{
        if (e.target.value) location.href = e.target.value;
      }});
      refresh();
      setInterval(refresh, 10000);
    }})();
  </script>
</body>
</html>"""

