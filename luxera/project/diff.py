from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

from luxera.project.schema import Project


DiffOpKind = Literal[
    "geometry_meta",
    "room",
    "surface",
    "opening",
    "obstruction",
    "level",
    "escape_route",
    "luminaire",
    "grid",
    "job",
    "material",
    "asset",
    "family",
    "variant",
]


@dataclass(frozen=True)
class DiffOp:
    op: Literal["add", "update", "remove"]
    kind: DiffOpKind
    id: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectDiff:
    ops: List[DiffOp] = field(default_factory=list)

    def apply(self, project: Project) -> Project:
        for op in self.ops:
            _apply_op(project, op)
        return project


def _apply_op(project: Project, op: DiffOp) -> None:
    if op.kind == "geometry_meta":
        current = project.geometry
        if op.op != "update":
            return
        for k, v in op.payload.items():
            setattr(current, k, v)
        return
    collection = _get_collection(project, op.kind)
    if op.op == "add":
        collection.append(op.payload)
        return
    if op.op == "remove":
        idx = _find_index(collection, op.id)
        if idx is not None:
            collection.pop(idx)
        return
    if op.op == "update":
        idx = _find_index(collection, op.id)
        if idx is None:
            return
        current = collection[idx]
        if hasattr(current, "__dict__"):
            for k, v in op.payload.items():
                setattr(current, k, v)
        else:
            current.update(op.payload)
        return


def _get_collection(project: Project, kind: DiffOpKind):
    if kind == "geometry_meta":
        return [project.geometry]
    if kind == "room":
        return project.geometry.rooms
    if kind == "surface":
        return project.geometry.surfaces
    if kind == "opening":
        return project.geometry.openings
    if kind == "obstruction":
        return project.geometry.obstructions
    if kind == "level":
        return project.geometry.levels
    if kind == "escape_route":
        return project.escape_routes
    if kind == "luminaire":
        return project.luminaires
    if kind == "grid":
        return project.grids
    if kind == "job":
        return project.jobs
    if kind == "material":
        return project.materials
    if kind == "asset":
        return project.photometry_assets
    if kind == "family":
        return project.luminaire_families
    if kind == "variant":
        return project.variants
    raise ValueError(f"Unsupported diff kind: {kind}")


def _find_index(collection, item_id: str):
    for i, item in enumerate(collection):
        if hasattr(item, "id") and item.id == item_id:
            return i
        if isinstance(item, dict) and item.get("id") == item_id:
            return i
    return None
