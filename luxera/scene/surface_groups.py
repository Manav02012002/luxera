from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Set

from luxera.project.schema import Project, SurfaceSpec


@dataclass(frozen=True)
class SurfaceSelection:
    ids: List[str]


def select_all_walls_in_room(project: Project, room_id: str) -> SurfaceSelection:
    ids = [s.id for s in project.geometry.surfaces if s.kind == "wall" and s.room_id == room_id]
    return SurfaceSelection(ids=sorted(ids))


def select_all_ceilings_on_storey(project: Project, level_id: str) -> SurfaceSelection:
    room_ids = {r.id for r in project.geometry.rooms if r.level_id == level_id}
    ids = [s.id for s in project.geometry.surfaces if s.kind == "ceiling" and s.room_id in room_ids]
    return SurfaceSelection(ids=sorted(ids))


def select_by_tag_layer_material(
    project: Project,
    *,
    tags_any: Optional[Sequence[str]] = None,
    layer: Optional[str] = None,
    material_id: Optional[str] = None,
) -> SurfaceSelection:
    tags = {str(t) for t in (tags_any or [])}
    out: List[str] = []
    for s in project.geometry.surfaces:
        if layer is not None and str(getattr(s, "layer", "") or "") != str(layer):
            continue
        if material_id is not None and str(s.material_id or "") != str(material_id):
            continue
        stags: Set[str] = set(str(t) for t in (getattr(s, "tags", []) or []))
        if tags and stags.isdisjoint(tags):
            continue
        out.append(s.id)
    return SurfaceSelection(ids=sorted(out))


def resolve_surface_set(project: Project, selectors: Iterable[SurfaceSelection]) -> SurfaceSelection:
    merged: Set[str] = set()
    for sel in selectors:
        merged.update(sel.ids)
    return SurfaceSelection(ids=sorted(merged))

