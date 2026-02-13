from __future__ import annotations

from dataclasses import dataclass
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


class TransactionManager:
    def __init__(self, project: Project) -> None:
        self.project = project
        self._active: Optional[Dict[str, Any]] = None
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

    def commit(self, *, before_hash: str = "", after_hash: str = "") -> TransactionRecord:
        if self._active is None:
            raise RuntimeError("no active transaction")
        before = self._active["before"]
        after = self.project.to_dict()
        delta = diff_project(before, after)
        rec = TransactionRecord(
            op_name=str(self._active["op_name"]),
            args=dict(self._active["args"]),
            delta=delta,
            before_hash=str(before_hash),
            after_hash=str(after_hash),
        )
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
    project.point_sets = restored.point_sets
    project.glare_views = restored.glare_views
    project.roadways = restored.roadways
    project.roadway_grids = restored.roadway_grids
    project.compliance_profiles = restored.compliance_profiles
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

