"""Register external-app tools as first-class Modoor MCP tools.

External apps (board / pulse / tms-iot) do not run their own MCP server.
They register ``artifacts.tools[].invoke_url``; Modoor mounts each tool on
``/mcp`` under its real name (e.g. ``tms-iot.list_devices``), same surface as
``fleet.query``.
"""

from __future__ import annotations

import inspect
import json
import keyword
import logging
from typing import Any, Callable

import httpx

from modoor.core.errors import AppError
from modoor.platform import services as app_registry
from modoor.platform.module_state import enabled_module_ids
from modoor.runtime.tool import run_tool

logger = logging.getLogger(__name__)

# Tool names this module currently owns on the MCP server (for refresh).
_managed: set[str] = set()


def _json_type(raw: Any) -> type:
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    if isinstance(raw, list) and raw:
        return _json_type(raw[0])
    return mapping.get(str(raw or "string"), str)


def _invoke(tool_name: str, arguments: dict[str, Any], *, readonly: bool) -> str:
    args = dict(arguments or {})

    def _inner(session, ctx, settings):
        hit = app_registry.find_tool(tool_name)
        if hit is None:
            raise AppError("not_found", f"tool not registered: {tool_name}")
        rec, tool = hit
        enabled = enabled_module_ids(session, ctx.tenant)
        if rec.module_id not in enabled:
            raise AppError("permission_denied", f"app disabled: {rec.module_id}")
        invoke_url = str(tool.get("invoke_url") or "").strip()
        if not invoke_url:
            raise AppError("validation_error", f"tool has no invoke_url: {tool_name}")
        payload = {"arguments": args}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-API-Key": settings.modoor_api_key,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(invoke_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise AppError("upstream_error", f"invoke failed: {exc}") from exc
        text = resp.text
        if resp.status_code >= 400:
            raise AppError(
                "upstream_error",
                f"invoke HTTP {resp.status_code}: {text[:400]}",
            )
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AppError("upstream_error", f"invalid JSON from {tool_name}") from exc
        if isinstance(data, dict) and data.get("status") in (
            "ok",
            "error",
            "needs_confirmation",
        ):
            return data
        return {"status": "ok", "result": data}

    return run_tool(tool_name, args, _inner, readonly=readonly)


def _safe_param_name(raw: str) -> str | None:
    name = str(raw or "").strip()
    if not name:
        return None
    if keyword.iskeyword(name) or not name.isidentifier():
        # JSON Schema keys like "from" / "to" → from_ / to_
        candidate = f"{name}_"
        if candidate.isidentifier() and not keyword.iskeyword(candidate):
            return candidate
        return None
    return name


def _make_proxy(item: dict[str, Any]) -> Callable[..., str]:
    name = str(item.get("name") or "").strip()
    description = str(item.get("description") or f"External tool {name}")
    schema = item.get("input_schema") or {"type": "object", "properties": {}}
    props = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(props, dict):
        props = {}
    required = set((schema.get("required") or []) if isinstance(schema, dict) else [])
    side = str(item.get("side_effects") or "read").lower()
    readonly = side == "read"

    # Map safe Python kwarg → original schema key
    param_to_arg: dict[str, str] = {}
    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {"return": str}
    for key, spec in props.items():
        safe = _safe_param_name(key)
        if safe is None:
            continue
        param_to_arg[safe] = key
        spec = spec if isinstance(spec, dict) else {}
        base = _json_type(spec.get("type"))
        if key in required:
            parameters.append(
                inspect.Parameter(
                    safe,
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=base,
                )
            )
            annotations[safe] = base
        else:
            opt = base | type(None)
            parameters.append(
                inspect.Parameter(
                    safe,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=None,
                    annotation=opt,
                )
            )
            annotations[safe] = opt

    # If schema had keys we could not map, expose a catch-all bag.
    if props and len(param_to_arg) < len(props):
        parameters.append(
            inspect.Parameter(
                "arguments",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=dict[str, Any] | None,
            )
        )
        annotations["arguments"] = dict[str, Any] | None

    def _impl(**kwargs: Any) -> str:
        cleaned: dict[str, Any] = {}
        extra = kwargs.pop("arguments", None)
        if isinstance(extra, dict):
            cleaned.update({k: v for k, v in extra.items() if v is not None})
        for safe, value in kwargs.items():
            if value is None:
                continue
            cleaned[param_to_arg.get(safe, safe)] = value
        return _invoke(name, cleaned, readonly=readonly)

    _impl.__name__ = name.replace(".", "_").replace("-", "_")
    _impl.__doc__ = description
    _impl.__signature__ = inspect.Signature(parameters, return_annotation=str)
    _impl.__annotations__ = annotations
    return _impl


def _tool_manager_tools(mcp) -> dict[str, Any]:
    mgr = getattr(mcp, "_tool_manager", None)
    if mgr is None:
        return {}
    return getattr(mgr, "_tools", {}) or {}


def sync_external_mcp_tools(mcp) -> list[str]:
    """Mount/remove MCP tools from registered external artifacts.

    Safe to call repeatedly (register / heartbeat / MCP startup).
    """
    desired: dict[str, dict[str, Any]] = {}
    for item in app_registry.aggregated_exports().get("tools") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or not str(item.get("invoke_url") or "").strip():
            continue
        desired[name] = item

    existing = _tool_manager_tools(mcp)

    for name in list(_managed):
        if name not in desired:
            try:
                mcp.remove_tool(name)
            except Exception:  # noqa: BLE001
                logger.debug("remove external tool %s failed", name, exc_info=True)
            _managed.discard(name)

    mounted: list[str] = []
    for name, item in desired.items():
        if name in existing and name not in _managed:
            # Built-in module tool wins.
            continue
        if name in _managed:
            try:
                mcp.remove_tool(name)
            except Exception:  # noqa: BLE001
                pass
            _managed.discard(name)
        fn = _make_proxy(item)
        mcp.add_tool(
            fn,
            name=name,
            description=str(item.get("description") or name),
            structured_output=False,
        )
        _managed.add(name)
        mounted.append(name)
    return mounted


def clear_managed_for_tests() -> None:
    _managed.clear()


def register(mcp) -> None:
    sync_external_mcp_tools(mcp)
