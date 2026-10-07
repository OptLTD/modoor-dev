"""Flow MCP tools."""

from __future__ import annotations

from typing import Any

from modoor.runtime.tool import run_tool
from builtin.flow import domain as flow_domain
from builtin.flow import engine as flow_engine


def emit(event_type: str, payload: dict[str, Any] | None = None) -> str:
    """Emit a flow event and start matching published definitions."""

    def _inner(session, ctx, _settings):
        inst = flow_engine.emit(
            session, ctx, event_type=event_type, payload=payload or {}
        )
        return {"instance": inst}

    return run_tool("flow.emit", {"event_type": event_type, "payload": payload}, _inner)


def instance_query(status: str | None = None, limit: int = 50) -> str:
    def _inner(session, ctx, _settings):
        return flow_domain.list_instances(session, ctx, status=status, limit=limit)

    return run_tool(
        "flow.instance.query",
        {"status": status, "limit": limit},
        _inner,
        readonly=True,
    )


def task_query(status: str = "pending", limit: int = 50) -> str:
    def _inner(session, ctx, _settings):
        return flow_domain.list_tasks(session, ctx, status=status, limit=limit)

    return run_tool(
        "flow.task.query",
        {"status": status, "limit": limit},
        _inner,
        readonly=True,
    )


def task_decide(task_id: str, decision: str, comment: str = "") -> str:
    def _inner(session, ctx, _settings):
        return {
            "task": flow_engine.decide_task(
                session, ctx, task_id=task_id, decision=decision, comment=comment
            )
        }

    return run_tool(
        "flow.task.decide",
        {"task_id": task_id, "decision": decision, "comment": comment},
        _inner,
    )


def register(mcp) -> None:  # noqa: ANN001
    mcp.tool(name="flow.emit")(emit)
    mcp.tool(name="flow.instance.query")(instance_query)
    mcp.tool(name="flow.task.query")(task_query)
    mcp.tool(name="flow.task.decide")(task_decide)
