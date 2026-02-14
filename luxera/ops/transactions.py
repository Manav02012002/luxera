from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from luxera.ops.delta import Delta, apply_delta, invert
from luxera.ops.diff import diff_project
from luxera.project.io import _project_from_dict  # type: ignore[attr-defined]
from luxera.project.schema import Project


@dataclass(frozen=True)
class TransactionRecord:
    op_name: str
    args: Dict[str, Any]
    delta: Delta
    before_hash: str
    after_hash: str
    group_id: Optional[str] = None
    grouped_ops: List[str] = field(default_factory=list)


class TransactionManager:
    def __init__(self, project: Project) -> None:
        self.project = project
        self._active: Optional[Dict[str, Any]] = None
        self._group: Optional[Dict[str, Any]] = None
        self._undo: List[TransactionRecord] = []
        self._redo: List[TransactionRecord] = []

    def begin(self, op_name: str = "op", args: Optional[Dict[str, Any]] = None) -> None:
        if self._active is not None:
            raise RuntimeError("transaction already active")
        self._active = {
            "op_name": str(op_name),
            "args": dict(args or {}),
            "before": self.project.to_dict(),
        }

    def begin_group(self, group_id: str = "group", args: Optional[Dict[str, Any]] = None) -> None:
        if self._group is not None:
            raise RuntimeError("transaction group already active")
        self._group = {
            "group_id": str(group_id),
            "args": dict(args or {}),
            "before": self.project.to_dict(),
            "before_hash": "",
            "records": [],
        }

    def end_group(self, *, before_hash: str = "", after_hash: str = "") -> Optional[TransactionRecord]:
        if self._group is None:
            raise RuntimeError("no active transaction group")
        grp = self._group
        self._group = None
        records: List[TransactionRecord] = list(grp.get("records", []))
        if not records:
            return None
        before = grp["before"]
        after = self.project.to_dict()
        base_delta = diff_project(before, after)
        # Merge metadata from grouped records.
        stable: Dict[str, List[str]] = {}
        attach: Dict[str, str] = {}
        regen_ids: set[str] = set()
        for r in records:
            stable.update(r.delta.stable_id_map)
            attach.update(r.delta.attachment_remap)
            for x in list(r.delta.derived_regen_summary.get("regenerated_ids", [])):
                regen_ids.add(str(x))
        delta = Delta(
            created=list(base_delta.created),
            updated=list(base_delta.updated),
            deleted=list(base_delta.deleted),
            param_changes=dict(base_delta.param_changes),
            derived_regen_summary={
                "regenerated_ids": sorted(regen_ids),
                "count": len(regen_ids),
                "group_id": str(grp["group_id"]),
            },
            stable_id_map=stable,
            attachment_remap=attach,
        )
        rec = TransactionRecord(
            op_name=str(grp["group_id"]),
            args=dict(grp["args"]),
            delta=delta,
            before_hash=str(before_hash),
            after_hash=str(after_hash),
            group_id=str(grp["group_id"]),
            grouped_ops=[r.op_name for r in records],
        )
        self._undo.append(rec)
        self._redo.clear()
        return rec

    def commit(
        self,
        *,
        before_hash: str = "",
        after_hash: str = "",
        stable_id_map: Optional[Dict[str, List[str]]] = None,
        attachment_remap: Optional[Dict[str, str]] = None,
        derived_regen_summary: Optional[Dict[str, Any]] = None,
    ) -> TransactionRecord:
        if self._active is None:
            raise RuntimeError("no active transaction")
        before = self._active["before"]
        after = self.project.to_dict()
        base_delta = diff_project(before, after)
        delta = Delta(
            created=list(base_delta.created),
            updated=list(base_delta.updated),
            deleted=list(base_delta.deleted),
            param_changes=dict(base_delta.param_changes),
            derived_regen_summary=dict(derived_regen_summary or base_delta.derived_regen_summary),
            stable_id_map={str(k): [str(x) for x in v] for k, v in (stable_id_map or base_delta.stable_id_map).items()},
            attachment_remap={str(k): str(v) for k, v in (attachment_remap or base_delta.attachment_remap).items()},
        )
        rec = TransactionRecord(
            op_name=str(self._active["op_name"]),
            args=dict(self._active["args"]),
            delta=delta,
            before_hash=str(before_hash),
            after_hash=str(after_hash),
            grouped_ops=[],
        )
        if self._group is not None:
            self._group["records"].append(rec)
        else:
            self._undo.append(rec)
            self._redo.clear()
        self._active = None
        return rec

    def rollback(self) -> None:
        if self._active is None:
            raise RuntimeError("no active transaction")
        restored = _project_from_dict(self._active["before"])
        _copy_project_state(self.project, restored)
        self._active = None

    def undo(self) -> bool:
        if not self._undo:
            return False
        rec = self._undo.pop()
        apply_delta(self.project, invert(rec.delta))
        self._redo.append(rec)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        rec = self._redo.pop()
        apply_delta(self.project, rec.delta)
        self._undo.append(rec)
        return True

    @property
    def undo_depth(self) -> int:
        return len(self._undo)

    @property
    def redo_depth(self) -> int:
        return len(self._redo)

    @property
    def active(self) -> bool:
        return self._active is not None

    @property
    def group_active(self) -> bool:
        return self._group is not None


def _copy_project_state(project: Project, restored: Project) -> None:
    project.geometry = restored.geometry
    project.materials = restored.materials
    project.material_library = restored.material_library
    project.photometry_assets = restored.photometry_assets
    project.luminaire_families = restored.luminaire_families
    project.luminaires = restored.luminaires
    project.grids = restored.grids
    project.workplanes = restored.workplanes
    project.vertical_planes = restored.vertical_planes
    project.arbitrary_planes = restored.arbitrary_planes
    project.point_sets = restored.point_sets
    project.line_grids = restored.line_grids
    project.glare_views = restored.glare_views
    project.escape_routes = restored.escape_routes
    project.roadways = restored.roadways
    project.roadway_grids = restored.roadway_grids
    project.compliance_profiles = restored.compliance_profiles
    project.symbols_2d = restored.symbols_2d
    project.block_instances = restored.block_instances
    project.selection_sets = restored.selection_sets
    project.layers = restored.layers
    project.variants = restored.variants
    project.active_variant_id = restored.active_variant_id
    project.jobs = restored.jobs
    project.results = restored.results
    project.param = restored.param


def get_transaction_manager(project: Project) -> TransactionManager:
    mgr = getattr(project, "_ops_transaction_manager", None)
    if mgr is None:
        mgr = TransactionManager(project)
        setattr(project, "_ops_transaction_manager", mgr)
    return mgr
