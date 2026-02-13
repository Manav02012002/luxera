from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from luxera.io.ifc_import import IFCImportOptions, ImportedIFC, import_ifc
from luxera.ifc.rooms import build_scene_rooms
from luxera.scene.scene_graph import SceneGraph, SceneNode, SceneTransform


@dataclass(frozen=True)
class DeterministicIFCImportResult:
    imported: ImportedIFC
    scene_graph: SceneGraph
    semantic_groups: Dict[str, List[str]] = field(default_factory=dict)


def _build_scene_graph(imported: ImportedIFC) -> SceneGraph:
    g = SceneGraph()
    g.add_node(SceneNode(id="root:ifc", name="IFC Root", type="group"))
    g.add_node(SceneNode(id="group:levels", name="Storeys", type="group", parent="root:ifc"))
    for lvl in imported.levels:
        g.add_node(
            SceneNode(
                id=f"level:{lvl.id}",
                name=lvl.name,
                type="level",
                parent="group:levels",
                local_transform=SceneTransform.from_translation((0.0, 0.0, float(lvl.elevation))),
                tags={"elevation": float(lvl.elevation)},
            )
        )
    g.add_node(SceneNode(id="group:spaces", name="Spaces", type="group", parent="root:ifc"))
    for room in imported.rooms:
        g.add_node(
            SceneNode(
                id=f"room:{room.id}",
                name=room.name,
                type="room",
                parent="group:spaces",
                local_transform=SceneTransform.from_translation(tuple(float(v) for v in room.origin)),
                tags={"width": float(room.width), "length": float(room.length), "height": float(room.height)},
            )
        )
    g.add_node(SceneNode(id="group:surfaces", name="Surfaces", type="group", parent="root:ifc"))
    for s in imported.surfaces:
        parent = f"room:{s.room_id}" if s.room_id else "group:surfaces"
        if parent != "group:surfaces":
            try:
                _ = g.get_node(parent)
            except KeyError:
                parent = "group:surfaces"
        g.add_node(
            SceneNode(
                id=f"surface:{s.id}",
                name=s.name,
                type=s.kind,
                parent=parent,
                mesh_ref=s.id,
                material_ref=s.material_id,
                tags={"room_id": s.room_id},
            )
        )
    g.add_node(SceneNode(id="group:openings", name="Openings", type="group", parent="root:ifc"))
    for o in imported.openings:
        parent = f"surface:{o.host_surface_id}" if o.host_surface_id else "group:openings"
        if parent != "group:openings":
            try:
                _ = g.get_node(parent)
            except KeyError:
                parent = "group:openings"
        g.add_node(
            SceneNode(
                id=f"opening:{o.id}",
                name=o.name,
                type=o.kind,
                parent=parent,
                mesh_ref=o.id,
                tags={"host_surface_id": o.host_surface_id, "visible_transmittance": o.visible_transmittance},
            )
        )
    g.rooms = build_scene_rooms(imported.rooms, imported.surfaces)
    return g


def import_ifc_deterministic(path: Path, options: IFCImportOptions | None = None) -> DeterministicIFCImportResult:
    imported = import_ifc(path, options=options)
    graph = _build_scene_graph(imported)
    groups: Dict[str, List[str]] = {
        "levels": [f"level:{x.id}" for x in imported.levels],
        "spaces": [f"room:{x.id}" for x in imported.rooms],
        "surfaces": [f"surface:{x.id}" for x in imported.surfaces],
        "openings": [f"opening:{x.id}" for x in imported.openings],
    }
    return DeterministicIFCImportResult(imported=imported, scene_graph=graph, semantic_groups=groups)
