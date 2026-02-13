from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from luxera.project.io import _project_from_dict  # type: ignore[attr-defined]
from luxera.project.schema import Project


@dataclass(frozen=True)
class DeltaItem:
    kind: str
    id: str
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class Delta:
    created: List[DeltaItem] = field(default_factory=list)
    updated: List[DeltaItem] = field(default_factory=list)
    deleted: List[DeltaItem] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.created and not self.updated and not self.deleted


def invert(delta: Delta) -> Delta:
    return Delta(
        created=[DeltaItem(kind=i.kind, id=i.id, before=i.after, after=i.before) for i in delta.deleted],
        updated=[DeltaItem(kind=i.kind, id=i.id, before=i.after, after=i.before) for i in delta.updated],
        deleted=[DeltaItem(kind=i.kind, id=i.id, before=i.after, after=i.before) for i in delta.created],
    )


def _index_by_id(collection: Any) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for idx, item in enumerate(collection):
        if hasattr(item, "id"):
            out[str(item.id)] = idx
        elif isinstance(item, dict) and "id" in item:
            out[str(item["id"])] = idx
    return out


def _resolve_collection(project: Project, kind: str) -> Any:
    if kind == "room":
        return project.geometry.rooms
    if kind == "surface":
        return project.geometry.surfaces
    if kind == "opening":
        return project.geometry.openings
    if kind == "material":
        return project.materials
    if kind == "grid":
        return project.grids
    if kind == "workplane":
        return project.workplanes
    if kind == "vertical_plane":
        return project.vertical_planes
    if kind == "point_set":
        return project.point_sets
    raise ValueError(f"Unsupported delta kind: {kind}")


def _replace_project_state(project: Project, restored: Project) -> None:
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


def _construct_item(project: Project, kind: str, payload: Dict[str, Any]) -> Any:
    tmp = Project(name="delta_tmp")
    coll = _resolve_collection(tmp, kind)
    if coll:
        # Keep mypy happy if default collection is unexpectedly non-empty.
        coll.clear()
    current = _resolve_collection(project, kind)
    if current:
        cls = type(current[0])
        return cls(**payload)
    # Fall back by round-tripping through loader for exact schema behavior.
    pd = project.to_dict()
    target = None
    if kind == "room":
        target = pd["geometry"]["rooms"]
    elif kind == "surface":
        target = pd["geometry"]["surfaces"]
    elif kind == "opening":
        target = pd["geometry"]["openings"]
    elif kind == "material":
        target = pd["materials"]
    elif kind == "grid":
        target = pd["grids"]
    elif kind == "workplane":
        target = pd["workplanes"]
    elif kind == "vertical_plane":
        target = pd["vertical_planes"]
    elif kind == "point_set":
        target = pd["point_sets"]
    else:
        raise ValueError(f"Unsupported delta kind: {kind}")
    target.append(dict(payload))
    restored = _project_from_dict(pd)
    return _resolve_collection(restored, kind)[-1]


def apply_delta(project: Project, delta: Delta) -> None:
    # Apply in stable order: deletes, updates, creates.
    for item in delta.deleted:
        coll = _resolve_collection(project, item.kind)
        idx = _index_by_id(coll).get(item.id)
        if idx is not None:
            coll.pop(idx)
    for item in delta.updated:
        if item.after is None:
            continue
        coll = _resolve_collection(project, item.kind)
        idx = _index_by_id(coll).get(item.id)
        if idx is None:
            continue
        coll[idx] = _construct_item(project, item.kind, item.after)
    for item in delta.created:
        if item.after is None:
            continue
        coll = _resolve_collection(project, item.kind)
        if _index_by_id(coll).get(item.id) is None:
            coll.append(_construct_item(project, item.kind, item.after))

