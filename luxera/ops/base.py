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
        stable_id_map = None
        attachment_remap = None
        derived_regen_summary = None
        if hasattr(out, "stable_id_map"):
            stable_id_map = getattr(out, "stable_id_map")
            attachment_remap = getattr(out, "attachment_remap", None)
            regen = getattr(out, "regenerated", None)
            derived_regen_summary = {
                "regenerated_ids": sorted(str(x) for x in (regen or [])),
                "count": len(regen or []),
            }
        after = project_hash(project)
        rec = txm.commit(
            before_hash=before,
            after_hash=after,
            stable_id_map=stable_id_map,
            attachment_remap=attachment_remap,
            derived_regen_summary=derived_regen_summary,
        )
        evt_args = dict(args)
        evt_args["tx"] = {
            "created": len(rec.delta.created),
            "updated": len(rec.delta.updated),
            "deleted": len(rec.delta.deleted),
            "param_changes": dict(rec.delta.param_changes),
            "derived_regen_summary": dict(rec.delta.derived_regen_summary),
            "stable_id_map_count": len(rec.delta.stable_id_map),
        }
        record_event(project, op_name=op_name, args=evt_args, ctx=context, before_hash=before, after_hash=after)
        return out
    except Exception:
        txm.rollback()
        raise
