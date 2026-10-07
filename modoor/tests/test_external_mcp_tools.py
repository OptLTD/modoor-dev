from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from modoor.core.settings import get_settings
from modoor.engine.registry import clear_bundle_cache
from modoor.engine.service import reload_engine_caches
from modoor.platform.bootstrap import bootstrap
from modoor.platform import services as app_registry
from modoor.runtime import external_tools
from modoor.runtime.mcp_server import mcp
from modoor.testing import configure_test_db
from modoor.web.nav import clear_ui_cache


@pytest.fixture()
def db(monkeypatch):
    configure_test_db(
        monkeypatch,
        MODOOR_API_KEY="test-key",
        MODOOR_TENANT="demo",
        MODOOR_CONFIRM_SECRET="secret",
        MODOOR_ADMIN_USERNAME="admin",
        MODOOR_ADMIN_PASSWORD="admin123",
    )
    get_settings.cache_clear()
    clear_ui_cache()
    clear_bundle_cache()
    reload_engine_caches()
    app_registry.clear_live_services()
    external_tools.clear_managed_for_tests()
    bootstrap()
    yield
    # Drop any tools this test mounted onto the process-global mcp.
    for name in list(getattr(external_tools, "_managed", set())):
        try:
            mcp.remove_tool(name)
        except Exception:
            pass
    external_tools.clear_managed_for_tests()
    app_registry.clear_live_services()
    get_settings.cache_clear()


def _register_tms_iot() -> None:
    app_registry.register_service(
        service_id="tms-iot",
        module_id="tms-iot",
        app_name="车联网",
        entry_url="http://127.0.0.1:8089/monitor",
        health_url="http://127.0.0.1:8088/health",
        manifest={
            "id": "tms-iot",
            "summary": "JT808 monitor",
            "exports": {
                "tools": [
                    "tms-iot.list_devices",
                    "tms-iot.list_routes",
                    "tms-iot.list_addresses",
                    "tms-iot.get_track",
                ],
                "skills": ["tms-iot.assist_ops"],
            },
            "ui-web": {"kind": "external", "label": "IoT"},
        },
        artifacts={
            "tools": [
                {
                    "name": "tms-iot.list_devices",
                    "description": "List devices",
                    "side_effects": "read",
                    "risk": "low",
                    "invoke_url": "http://127.0.0.1:8088/modoor/tools/tms-iot.list_devices",
                },
                {
                    "name": "tms-iot.get_track",
                    "description": "Get track",
                    "side_effects": "read",
                    "risk": "low",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "string"},
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                        },
                        "required": ["device_id"],
                    },
                    "invoke_url": "http://127.0.0.1:8088/modoor/tools/tms-iot.get_track",
                },
            ],
            "skills": [
                {
                    "id": "tms-iot.assist_ops",
                    "title": "Assist IoT",
                    "tools": ["tms-iot.list_devices"],
                }
            ],
        },
    )


def test_tms_iot_tools_mount_as_first_class_mcp(db):
    _register_tms_iot()
    mounted = external_tools.sync_external_mcp_tools(mcp)
    assert "tms-iot.list_devices" in mounted

    tools = mcp._tool_manager._tools
    assert "tms-iot.list_devices" in tools
    assert "tms-iot.get_track" in tools
    assert "external.call_tool" not in tools
    assert "catalog.list_capabilities" not in tools

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"status":"ok","result":{"items":[],"count":0}}'
    mock_resp.json.return_value = {"status": "ok", "result": {"items": [], "count": 0}}

    with patch("modoor.runtime.external_tools.httpx.Client") as client_cls:
        instance = client_cls.return_value.__enter__.return_value
        instance.post.return_value = mock_resp
        out = json.loads(tools["tms-iot.list_devices"].fn())

    assert out["status"] == "ok"
    assert out["result"]["count"] == 0
    args, kwargs = instance.post.call_args
    assert args[0] == "http://127.0.0.1:8088/modoor/tools/tms-iot.list_devices"
    assert kwargs["headers"]["X-API-Key"] == "test-key"


def test_unknown_external_tool_not_mounted(db):
    _register_tms_iot()
    external_tools.sync_external_mcp_tools(mcp)
    assert "tms-iot.does_not_exist" not in mcp._tool_manager._tools
