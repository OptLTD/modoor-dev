"""Flow graph runner.

Graph JSON:
  nodes: [{id, type, config?}, ...]
  edges: [{from, to, when?}, ...]

Node types: start | end | action | condition | approval | extract | score | delay
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from modoor.core.ctx import Ctx
from modoor.core.errors import AppError
from modoor.runtime.jobs import enqueue
from builtin.flow import domain as flow_domain
from builtin.flow.domain import FlowDefinition, FlowInstance, FlowTask, _new_id, _now


def _nodes_by_id(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(n.get("id")): n for n in (graph.get("nodes") or []) if n.get("id")}


def _start_node(graph: dict[str, Any]) -> str:
    for n in graph.get("nodes") or []:
        if n.get("type") == "start":
            return str(n["id"])
    raise AppError("validation_error", "flow graph missing start node")


def _eval_when(expr: str | None, context: dict[str, Any]) -> bool:
    if not expr or not str(expr).strip():
        return True
    text = str(expr).strip()
    # score >= 60 / score_ok == true / context.key
    m = re.fullmatch(
        r"([a-zA-Z_][\w.]*)\s*(>=|<=|==|!=|>|<)\s*(.+)",
        text,
    )
    if not m:
        # bare truthy key
        return bool(_ctx_get(context, text))
    left, op, right_raw = m.group(1), m.group(2), m.group(3).strip()
    left_val = _ctx_get(context, left)
    right_val: Any
    if right_raw.lower() in ("true", "false"):
        right_val = right_raw.lower() == "true"
    else:
        try:
            right_val = float(right_raw) if "." in right_raw else int(right_raw)
        except ValueError:
            right_val = right_raw.strip("'\"")
    try:
        if op == ">=":
            return left_val >= right_val
        if op == "<=":
            return left_val <= right_val
        if op == ">":
            return left_val > right_val
        if op == "<":
            return left_val < right_val
        if op == "==":
            return left_val == right_val
        if op == "!=":
            return left_val != right_val
    except TypeError:
        return False
    return False


def _ctx_get(context: dict[str, Any], path: str) -> Any:
    cur: Any = context
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _next_nodes(
    graph: dict[str, Any], node_id: str, context: dict[str, Any]
) -> list[str]:
    outs: list[tuple[str, str | None]] = []
    for e in graph.get("edges") or []:
        if str(e.get("from")) != node_id:
            continue
        outs.append((str(e.get("to")), e.get("when")))
    matched = [t for t, w in outs if _eval_when(w, context)]
    if matched:
        return matched
    # default edges without when
    return [t for t, w in outs if not w]


def emit(
    session: Session,
    ctx: Ctx,
    *,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Start published definitions whose trigger.event matches."""
    payload = dict(payload or {})
    rows = list(
        session.scalars(
            select(FlowDefinition).where(
                FlowDefinition.tenant == ctx.tenant,
                FlowDefinition.status == "published",
            )
        )
    )
    started = None
    for row in rows:
        trig = row.trigger or {}
        if str(trig.get("event") or "") != event_type:
            continue
        started = start_instance(
            session,
            ctx,
            definition=row,
            context=payload,
            ref_model=str(payload.get("ref_model") or ""),
            ref_id=str(payload.get("ref_id") or ""),
        )
    return started


def start_instance(
    session: Session,
    ctx: Ctx,
    *,
    definition: FlowDefinition | None = None,
    definition_key: str | None = None,
    context: dict[str, Any] | None = None,
    ref_model: str = "",
    ref_id: str = "",
) -> dict[str, Any]:
    if definition is None:
        definition = flow_domain._load_definition(
            session, ctx, key=definition_key, published_only=True
        )
    graph = definition.graph or {}
    start = _start_node(graph)
    inst = FlowInstance(
        id=_new_id(),
        tenant=ctx.tenant,
        definition_id=definition.id,
        definition_key=definition.key,
        status="running",
        current_node=start,
        context=dict(context or {}),
        ref_model=ref_model,
        ref_id=ref_id,
        created_by=ctx.user_id,
    )
    session.add(inst)
    session.flush()
    flow_domain.append_log(
        session,
        tenant=ctx.tenant,
        instance_id=inst.id,
        node_id=start,
        event="started",
        detail={"definition_key": definition.key},
    )
    enqueue(session, kind="flow.advance", payload={"instance_id": inst.id})
    return flow_domain._inst_dict(inst)


def advance(session: Session, *, instance_id: str) -> None:
    inst = session.get(FlowInstance, instance_id)
    if inst is None or inst.status not in ("running", "waiting"):
        return
    definition = session.get(FlowDefinition, inst.definition_id)
    if definition is None:
        inst.status = "failed"
        flow_domain.append_log(
            session,
            tenant=inst.tenant,
            instance_id=inst.id,
            node_id=inst.current_node,
            event="failed",
            error="definition missing",
        )
        return
    graph = definition.graph or {}
    nodes = _nodes_by_id(graph)
    ctx = Ctx(tenant=inst.tenant, user_id=inst.created_by, team_id=0)

    # safety: max steps per advance call
    for _ in range(32):
        if inst.status != "running":
            return
        node = nodes.get(inst.current_node)
        if node is None:
            inst.status = "failed"
            flow_domain.append_log(
                session,
                tenant=inst.tenant,
                instance_id=inst.id,
                node_id=inst.current_node,
                event="failed",
                error="unknown node",
            )
            return
        ntype = str(node.get("type") or "")
        config = node.get("config") or {}
        flow_domain.append_log(
            session,
            tenant=inst.tenant,
            instance_id=inst.id,
            node_id=inst.current_node,
            event="enter",
            detail={"type": ntype},
        )
        if ntype == "start":
            _goto_next(session, inst, graph)
            continue
        if ntype == "end":
            inst.status = "completed"
            inst.updated_at = _now()
            flow_domain.append_log(
                session,
                tenant=inst.tenant,
                instance_id=inst.id,
                node_id=inst.current_node,
                event="completed",
            )
            return
        if ntype == "condition":
            # edges carry when; just follow
            _goto_next(session, inst, graph)
            continue
        if ntype == "delay":
            from datetime import timedelta

            seconds = int(config.get("seconds") or 0)
            enqueue(
                session,
                kind="flow.advance",
                payload={"instance_id": inst.id},
            )
            # mark waiting then bump node after re-queue — simplify: sleep via run_after
            from modoor.runtime.jobs import Job

            job = (
                session.scalars(
                    select(Job)
                    .where(Job.kind == "flow.advance")
                    .order_by(Job.created_at.desc())
                ).first()
            )
            if job and seconds > 0:
                job.run_after = _now() + timedelta(seconds=seconds)
            inst.status = "waiting"
            inst.updated_at = _now()
            # move pointer now so resume continues after delay node
            nxt = _next_nodes(graph, inst.current_node, inst.context or {})
            if nxt:
                inst.current_node = nxt[0]
            return
        if ntype == "extract":
            _run_extract(session, ctx, inst, config)
            if inst.status == "waiting":
                return
            _goto_next(session, inst, graph)
            continue
        if ntype == "score":
            _run_score(session, inst, config)
            _goto_next(session, inst, graph)
            continue
        if ntype == "approval":
            _open_approval(session, inst, node, config)
            return
        if ntype == "action":
            _run_action(session, ctx, inst, config)
            _goto_next(session, inst, graph)
            continue
        # unknown → skip
        _goto_next(session, inst, graph)


def _goto_next(session: Session, inst: FlowInstance, graph: dict[str, Any]) -> None:
    nxt = _next_nodes(graph, inst.current_node, inst.context or {})
    if not nxt:
        inst.status = "completed"
        inst.updated_at = _now()
        return
    inst.current_node = nxt[0]
    inst.status = "running"
    inst.updated_at = _now()
    session.flush()


def _run_extract(
    session: Session, ctx: Ctx, inst: FlowInstance, config: dict[str, Any]
) -> None:
    asset_id = str(
        (inst.context or {}).get("asset_id")
        or config.get("asset_id")
        or ""
    ).strip()
    if not asset_id:
        flow_domain.append_log(
            session,
            tenant=inst.tenant,
            instance_id=inst.id,
            node_id=inst.current_node,
            event="extract_skip",
            detail={"reason": "no asset_id"},
        )
        return
    from builtin.doc import domain as doc_domain

    asset = doc_domain.get_asset(session, ctx, asset_id=asset_id, include_text=True)
    status = asset.get("text_status") or "ready"
    if status in ("pending", "running"):
        inst.status = "waiting"
        enqueue(
            session,
            kind="flow.wait_doc_extract",
            payload={"instance_id": inst.id, "asset_id": asset_id},
        )
        return
    ctx_data = dict(inst.context or {})
    ctx_data["doc_text"] = asset.get("text") or ""
    ctx_data["doc_text_status"] = status
    inst.context = ctx_data
    session.flush()


def _run_score(session: Session, inst: FlowInstance, config: dict[str, Any]) -> None:
    ctx_data = dict(inst.context or {})
    required = list(config.get("required_doc_types") or [])
    present = list(ctx_data.get("doc_types") or [])
    text = str(ctx_data.get("doc_text") or "")
    score = 0
    detail: dict[str, Any] = {"checks": []}
    if required:
        hit = sum(1 for t in required if t in present)
        part = int(100 * hit / max(len(required), 1))
        score += part // 2
        detail["checks"].append({"required_types": required, "present": present, "part": part // 2})
    else:
        score += 40
    keywords = list(config.get("keywords") or ["营业执照", "公司", "统一社会信用"])
    kw_hit = sum(1 for k in keywords if k in text)
    kw_part = int(50 * kw_hit / max(len(keywords), 1)) if keywords else 30
    score += kw_part
    detail["checks"].append({"keywords": keywords, "hits": kw_hit, "part": kw_part})
    if len(text) >= int(config.get("min_text_chars") or 20):
        score += 10
        detail["checks"].append({"min_text": True, "part": 10})
    score = max(0, min(100, score))
    threshold = int(config.get("threshold") or 60)
    ctx_data["score"] = score
    ctx_data["score_detail"] = detail
    ctx_data["score_ok"] = score >= threshold
    inst.context = ctx_data
    session.flush()
    flow_domain.append_log(
        session,
        tenant=inst.tenant,
        instance_id=inst.id,
        node_id=inst.current_node,
        event="scored",
        detail={"score": score, "threshold": threshold, "ok": ctx_data["score_ok"]},
    )


def _open_approval(
    session: Session, inst: FlowInstance, node: dict[str, Any], config: dict[str, Any]
) -> None:
    levels = config.get("levels") or [{"role": "admin"}]
    # find first incomplete level
    existing = list(
        session.scalars(
            select(FlowTask).where(
                FlowTask.instance_id == inst.id,
                FlowTask.node_id == inst.current_node,
            )
        )
    )
    done_levels = {t.level for t in existing if t.status == "approved"}
    rejected = [t for t in existing if t.status == "rejected"]
    if rejected:
        ctx_data = dict(inst.context or {})
        ctx_data["approval_decision"] = "reject"
        inst.context = ctx_data
        inst.status = "running"
        _goto_next(session, inst, session.get(FlowDefinition, inst.definition_id).graph or {})
        enqueue(session, kind="flow.advance", payload={"instance_id": inst.id})
        return
    for idx, level in enumerate(levels):
        if idx in done_levels:
            continue
        pending = [
            t
            for t in existing
            if t.level == idx and t.status == "pending"
        ]
        if pending:
            inst.status = "waiting"
            return
        # create task for this level
        role = str((level or {}).get("role") or "")
        user = int((level or {}).get("user") or 0)
        task = FlowTask(
            id=_new_id(),
            tenant=inst.tenant,
            instance_id=inst.id,
            node_id=inst.current_node,
            level=idx,
            title=str(config.get("title") or node.get("label") or "Approval"),
            status="pending",
            assignee_role=role,
            assignee_user=user,
            form={"context": inst.context or {}},
        )
        session.add(task)
        session.flush()
        inst.status = "waiting"
        flow_domain.append_log(
            session,
            tenant=inst.tenant,
            instance_id=inst.id,
            node_id=inst.current_node,
            event="approval_opened",
            detail={"level": idx, "task_id": task.id},
        )
        return
    # all levels approved
    ctx_data = dict(inst.context or {})
    ctx_data["approval_decision"] = "approve"
    inst.context = ctx_data
    inst.status = "running"
    definition = session.get(FlowDefinition, inst.definition_id)
    _goto_next(session, inst, (definition.graph if definition else {}) or {})
    enqueue(session, kind="flow.advance", payload={"instance_id": inst.id})


def decide_task(
    session: Session,
    ctx: Ctx,
    *,
    task_id: str,
    decision: str,
    comment: str = "",
) -> dict[str, Any]:
    task = session.get(FlowTask, task_id)
    if task is None or task.tenant != ctx.tenant:
        raise AppError("not_found", "task not found")
    if task.status != "pending":
        raise AppError("validation_error", "task is not pending")
    decision = (decision or "").strip().lower()
    if decision not in ("approve", "reject"):
        raise AppError("validation_error", "decision must be approve|reject")
    task.decision = decision
    task.status = "approved" if decision == "approve" else "rejected"
    task.comment = comment or ""
    task.decided_by = ctx.user_id
    task.decided_at = _now()
    task.updated_at = _now()
    session.flush()
    inst = session.get(FlowInstance, task.instance_id)
    if inst is None:
        return flow_domain._task_dict(task)
    if decision == "reject":
        ctx_data = dict(inst.context or {})
        ctx_data["approval_decision"] = "reject"
        ctx_data["reject_reason"] = comment or "rejected"
        inst.context = ctx_data
        inst.status = "running"
        definition = session.get(FlowDefinition, inst.definition_id)
        graph = (definition.graph if definition else {}) or {}
        # follow reject edge if present
        reject_targets = [
            str(e.get("to"))
            for e in graph.get("edges") or []
            if str(e.get("from")) == task.node_id
            and str(e.get("when") or "").replace(" ", "")
            in ("approval_decision==reject", "decision==reject")
        ]
        if reject_targets:
            inst.current_node = reject_targets[0]
        else:
            _goto_next(session, inst, graph)
        enqueue(session, kind="flow.advance", payload={"instance_id": inst.id})
    else:
        # reopen approval node to advance levels / finish
        inst.current_node = task.node_id
        inst.status = "running"
        enqueue(session, kind="flow.advance", payload={"instance_id": inst.id})
    return flow_domain._task_dict(task)


def _run_action(
    session: Session, ctx: Ctx, inst: FlowInstance, config: dict[str, Any]
) -> None:
    action = str(config.get("action") or "").strip()
    if action == "capacity.set_document_audit":
        _action_set_document_audit(session, ctx, inst, config)
        return
    if action == "capacity.set_company_cert":
        _action_set_company_cert(session, ctx, inst, config)
        return
    flow_domain.append_log(
        session,
        tenant=inst.tenant,
        instance_id=inst.id,
        node_id=inst.current_node,
        event="action_noop",
        detail={"action": action},
    )


def _action_set_document_audit(
    session: Session, ctx: Ctx, inst: FlowInstance, config: dict[str, Any]
) -> None:
    status = str(config.get("audit_status") or "").strip()
    if not status:
        decision = str((inst.context or {}).get("approval_decision") or "")
        score_ok = bool((inst.context or {}).get("score_ok"))
        if decision == "reject" or (decision == "" and not score_ok):
            status = "rejected"
        else:
            status = "approved"
    doc_id = str(
        (inst.context or {}).get("document_id")
        or inst.ref_id
        or ""
    ).strip()
    reason = str(
        config.get("reject_reason")
        or (inst.context or {}).get("reject_reason")
        or ""
    )
    try:
        from addon.capacity import domain as capacity_domain

        if hasattr(capacity_domain, "set_document_audit"):
            capacity_domain.set_document_audit(
                session,
                ctx,
                document_id=doc_id,
                audit_status=status,
                reject_reason=reason,
            )
    except Exception as exc:  # noqa: BLE001
        flow_domain.append_log(
            session,
            tenant=inst.tenant,
            instance_id=inst.id,
            node_id=inst.current_node,
            event="action_error",
            error=str(exc),
        )
        return
    flow_domain.append_log(
        session,
        tenant=inst.tenant,
        instance_id=inst.id,
        node_id=inst.current_node,
        event="action_done",
        detail={"audit_status": status, "document_id": doc_id},
    )


def _action_set_company_cert(
    session: Session, ctx: Ctx, inst: FlowInstance, config: dict[str, Any]
) -> None:
    company_id = str((inst.context or {}).get("company_id") or "").strip()
    certified = config.get("certified")
    if certified is None:
        certified = str((inst.context or {}).get("approval_decision") or "") == "approve"
    try:
        from addon.capacity import domain as capacity_domain

        if hasattr(capacity_domain, "set_company_certified"):
            capacity_domain.set_company_certified(
                session, ctx, company_id=company_id, certified=bool(certified)
            )
    except Exception as exc:  # noqa: BLE001
        flow_domain.append_log(
            session,
            tenant=inst.tenant,
            instance_id=inst.id,
            node_id=inst.current_node,
            event="action_error",
            error=str(exc),
        )
