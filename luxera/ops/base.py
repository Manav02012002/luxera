from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any, Callable, Dict, Optional, TypeVar

from luxera.project.schema import Project
from luxera.ops.transactions import get_transaction_manager

T = TypeVar("T")


@dataclass(frozen=True)
class OpContext:
    user: str = "system"
    source: str = "gui"  # gui | agent | cli
    require_approval: bool = False
    approved: bool = True
    run_id: Optional[str] = None


def project_hash(project: Project) -> str:
    data = dict(project.to_dict())
    data.pop("agent_history", None)
    data.pop("assistant_undo_stack", None)
    data.pop("assistant_redo_stack", None)
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def record_event(
    project: Project,
    *,
    op_name: str,
    args: Dict[str, Any],
    ctx: OpContext,
    before_hash: str,
    after_hash: str,
) -> None:
    project.agent_history.append(
        {
            "action": f"ops.{op_name}",
            "source": ctx.source,
            "user": ctx.user,
            "run_id": ctx.run_id,
            "require_approval": bool(ctx.require_approval),
            "approved": bool(ctx.approved),
            "before_hash": before_hash,
            "after_hash": after_hash,
            "args": args,
        }
    )


def execute_op(
    project: Project,
    *,
    op_name: str,
    args: Dict[str, Any],
    ctx: Optional[OpContext],
    validate: Optional[Callable[[], None]],
    mutate: Callable[[], T],
) -> T:
    context = ctx or OpContext()
    if context.source == "agent" and context.require_approval and not context.approved:
        raise PermissionError(f"Operation {op_name} requires approval")
    if validate is not None:
        validate()
    before = project_hash(project)
    txm = get_transaction_manager(project)
    txm.begin(op_name=op_name, args=args)
    try:
        out = mutate()
        after = project_hash(project)
        rec = txm.commit(before_hash=before, after_hash=after)
        evt_args = dict(args)
        evt_args["tx"] = {
            "created": len(rec.delta.created),
            "updated": len(rec.delta.updated),
            "deleted": len(rec.delta.deleted),
        }
        record_event(project, op_name=op_name, args=evt_args, ctx=context, before_hash=before, after_hash=after)
        return out
    except Exception:
        txm.rollback()
        raise
