from __future__ import annotations

from typing import Optional

from luxera.project.schema import Project
from luxera.scene.scene_graph import SceneGraph, SceneNode, SceneTransform


def build_scene_graph_from_project(project: Project) -> SceneGraph:
    g = SceneGraph()
    g.add_node(SceneNode(id="root:project", name=project.name or "Project", type="project"))

    if project.geometry.levels:
        g.add_node(SceneNode(id="group:levels", name="Levels", type="group", parent="root:project"))
        for lvl in project.geometry.levels:
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

    g.add_node(SceneNode(id="group:rooms", name="Rooms", type="group", parent="root:project"))
    for room in project.geometry.rooms:
        parent = f"level:{room.level_id}" if room.level_id and any(x.id == room.level_id for x in project.geometry.levels) else "group:rooms"
        g.add_node(
            SceneNode(
                id=f"room:{room.id}",
                name=room.name,
                type="room",
                parent=parent,
                local_transform=SceneTransform.from_translation(tuple(float(v) for v in room.origin)),
                tags={"width": float(room.width), "length": float(room.length), "height": float(room.height)},
            )
        )

    for surface in project.geometry.surfaces:
        parent = f"room:{surface.room_id}" if surface.room_id else "group:rooms"
        if parent != "group:rooms" and not _has_node(g, parent):
            parent = "group:rooms"
        g.add_node(
            SceneNode(
                id=f"surface:{surface.id}",
                name=surface.name,
                type=surface.kind,
                parent=parent,
                mesh_ref=surface.id,
                material_ref=surface.material_id,
                tags={"room_id": surface.room_id},
            )
        )

    for opening in project.geometry.openings:
        parent = f"surface:{opening.host_surface_id}" if opening.host_surface_id else "group:rooms"
        if parent != "group:rooms" and not _has_node(g, parent):
            parent = "group:rooms"
        g.add_node(
            SceneNode(
                id=f"opening:{opening.id}",
                name=opening.name,
                type=opening.kind,
                parent=parent,
                mesh_ref=opening.id,
                tags={"host_surface_id": opening.host_surface_id},
            )
        )

    g.add_node(SceneNode(id="group:luminaires", name="Luminaires", type="group", parent="root:project"))
    for lum in project.luminaires:
        parent = "group:luminaires"
        if lum.family_id:
            fam_group = f"family:{lum.family_id}"
            if not _has_node(g, fam_group):
                g.add_node(SceneNode(id=fam_group, name=lum.family_id, type="group", parent=parent))
            parent = fam_group
        g.add_node(
            SceneNode(
                id=f"luminaire:{lum.id}",
                name=lum.name,
                type="luminaire",
                parent=parent,
                local_transform=SceneTransform.from_translation(tuple(float(v) for v in lum.transform.position)),
                mesh_ref=lum.family_id,
                instance_ref=lum.family_id,
                tags={"asset_id": lum.photometry_asset_id},
            )
        )

    g.add_node(SceneNode(id="group:calcs", name="Calc Objects", type="group", parent="root:project"))
    for grid in project.grids:
        g.add_node(
            SceneNode(
                id=f"grid:{grid.id}",
                name=grid.name,
                type="grid",
                parent="group:calcs",
                local_transform=SceneTransform.from_translation(tuple(float(v) for v in grid.origin)),
                tags={"nx": int(grid.nx), "ny": int(grid.ny)},
            )
        )
    return g


def _has_node(graph: SceneGraph, node_id: str) -> bool:
    try:
        graph.get_node(node_id)
        return True
    except KeyError:
        return False
