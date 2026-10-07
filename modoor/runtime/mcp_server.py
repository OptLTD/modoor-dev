from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from modoor.core.db import init_db
from modoor.platform.loader import register_module_tools

mcp = MCPServer(
    "modoor",
    version="0.1.0",
    instructions=(
        "modoor(木牍) system MCP server only. "
        "Hosts should install Skills from /agent/readme (HTTP) before calling tools. "
        "Prefer task-oriented tools (e.g. fleet.query / fleet.aggregate). "
        "External apps (e.g. tms-iot) register the same way: their tools appear "
        "as first-class MCP tools (tms-iot.list_devices, …) on this single /mcp port. "
        "Agent tokens may be read-only."
    ),
)


_registered = False


def ensure_tools_registered() -> None:
    global _registered
    init_db()
    if _registered:
        # External apps may register after startup — refresh their MCP tools.
        from modoor.runtime.external_tools import sync_external_mcp_tools

        sync_external_mcp_tools(mcp)
        return
    register_module_tools(mcp)
    from modoor.runtime.external_tools import register as register_external_tools

    register_external_tools(mcp)
    _registered = True


def main() -> None:
    ensure_tools_registered()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
