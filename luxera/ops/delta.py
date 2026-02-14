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
    param_changes: Dict[str, List[str]] = field(default_factory=dict)
    derived_regen_summary: Dict[str, Any] = field(default_factory=dict)
    stable_id_map: Dict[str, List[str]] = field(default_factory=dict)
    attachment_remap: Dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.created and not self.updated and not self.deleted


def invert(delta: Delta) -> Delta:
    inv_stable: Dict[str, List[str]] = {}
    for parent, children in delta.stable_id_map.items():
        if not children:
            continue
        for child in children:
            inv_stable.setdefault(str(child), []).append(str(parent))
    inv_attach: Dict[str, str] = {str(v): str(k) for k, v in delta.attachment_remap.items()}
    return Delta(
        created=[DeltaItem(kind=i.kind, id=i.id, before=i.after, after=i.before) for i in delta.deleted],
        updated=[DeltaItem(kind=i.kind, id=i.id, before=i.after, after=i.before) for i in delta.updated],
        deleted=[DeltaItem(kind=i.kind, id=i.id, before=i.after, after=i.before) for i in delta.created],
        param_changes={k: list(v) for k, v in delta.param_changes.items()},
        derived_regen_summary=dict(delta.derived_regen_summary),
        stable_id_map=inv_stable,
        attachment_remap=inv_attach,
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
    if kind == "line_grid":
        return project.line_grids
    if kind == "arbitrary_plane":
        return project.arbitrary_planes
    if kind == "glare_view":
        return project.glare_views
    if kind == "escape_route":
        return project.escape_routes
    if kind == "roadway":
        return project.roadways
    if kind == "roadway_grid":
        return project.roadway_grids
    if kind == "luminaire":
        return project.luminaires
    if kind == "asset":
        return project.photometry_assets
    if kind == "family":
        return project.luminaire_families
    if kind == "variant":
        return project.variants
    if kind == "layer":
        return project.layers
    if kind == "symbol_2d":
        return project.symbols_2d
    if kind == "block_instance":
        return project.block_instances
    if kind == "selection_set":
        return project.selection_sets
    if kind == "param_footprint":
        return project.param.footprints
    if kind == "param_room":
        return project.param.rooms
    if kind == "param_wall":
        return project.param.walls
    if kind == "param_shared_wall":
        return project.param.shared_walls
    if kind == "param_opening":
        return project.param.openings
    if kind == "param_slab":
        return project.param.slabs
    if kind == "param_zone":
        return project.param.zones
    if kind == "param_instance":
        return project.param.instances
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


def _construct_item(project: Project, kind: str, payload: Dict[str, Any]) -> Any:
    # Construct by round-tripping through loader for exact schema behavior
    # including nested dataclasses (e.g. transform specs).
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
    elif kind == "line_grid":
        target = pd["line_grids"]
    elif kind == "arbitrary_plane":
        target = pd["arbitrary_planes"]
    elif kind == "glare_view":
        target = pd["glare_views"]
    elif kind == "escape_route":
        target = pd["escape_routes"]
    elif kind == "roadway":
        target = pd["roadways"]
    elif kind == "roadway_grid":
        target = pd["roadway_grids"]
    elif kind == "luminaire":
        target = pd["luminaires"]
    elif kind == "asset":
        target = pd["photometry_assets"]
    elif kind == "family":
        target = pd["luminaire_families"]
    elif kind == "variant":
        target = pd["variants"]
    elif kind == "layer":
        target = pd["layers"]
    elif kind == "symbol_2d":
        target = pd["symbols_2d"]
    elif kind == "block_instance":
        target = pd["block_instances"]
    elif kind == "selection_set":
        target = pd["selection_sets"]
    elif kind == "param_footprint":
        target = pd["param"]["footprints"]
    elif kind == "param_room":
        target = pd["param"]["rooms"]
    elif kind == "param_wall":
        target = pd["param"]["walls"]
    elif kind == "param_shared_wall":
        target = pd["param"]["shared_walls"]
    elif kind == "param_opening":
        target = pd["param"]["openings"]
    elif kind == "param_slab":
        target = pd["param"]["slabs"]
    elif kind == "param_zone":
        target = pd["param"]["zones"]
    elif kind == "param_instance":
        target = pd["param"]["instances"]
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

    # Deterministic replay for param edits: regenerate derived geometry via param rebuild DAG.
    param_kinds = {
        "param_footprint": "footprint",
        "param_room": "room",
        "param_wall": "wall",
        "param_opening": "opening",
        "param_zone": "zone",
        "param_shared_wall": "shared_wall",
        "param_slab": "slab",
        "param_instance": "instance",
    }
    edited_ids: List[str] = []
    for it in list(delta.created) + list(delta.updated) + list(delta.deleted):
        ns = param_kinds.get(str(it.kind))
        if ns is not None:
            edited_ids.append(f"{ns}:{it.id}")
    if edited_ids:
        try:
            from luxera.geometry.param.rebuild import rebuild as _param_rebuild

            _param_rebuild(sorted(set(edited_ids)), project)
        except Exception:
            # Keep delta application robust even if rebuild is unavailable in minimal contexts.
            pass
