from __future__ import annotations

from typing import Dict, Tuple

from luxera.project.schema import Project, RotationSpec, TransformSpec


def resolve_scene_node_update(project: Project, scene_node_id: str, payload: Dict[str, object]) -> Tuple[str, str, Dict[str, object]]:
    if ":" not in scene_node_id:
        raise ValueError(f"Invalid scene node id: {scene_node_id}")
    prefix, oid = scene_node_id.split(":", 1)
    name = str(payload.get("name", "") or "")
    tx = float(payload.get("tx", 0.0) or 0.0)
    ty = float(payload.get("ty", 0.0) or 0.0)
    tz = float(payload.get("tz", 0.0) or 0.0)
    yaw = float(payload.get("yaw_deg", 0.0) or 0.0)
    pitch = float(payload.get("pitch_deg", 0.0) or 0.0)
    roll = float(payload.get("roll_deg", 0.0) or 0.0)
    material_id = str(payload.get("material_id", "") or "")

    if prefix == "room":
        room = next((r for r in project.geometry.rooms if r.id == oid), None)
        if room is None:
            raise ValueError(f"Unknown room: {oid}")
        upd: Dict[str, object] = {"origin": (tx, ty, tz)}
        if name:
            upd["name"] = name
        return ("room", oid, upd)

    if prefix == "surface":
        surface = next((s for s in project.geometry.surfaces if s.id == oid), None)
        if surface is None:
            raise ValueError(f"Unknown surface: {oid}")
        upd2: Dict[str, object] = {}
        if name:
            upd2["name"] = name
        if material_id:
            upd2["material_id"] = material_id
        if surface.vertices:
            vx = tx - float(surface.vertices[0][0])
            vy = ty - float(surface.vertices[0][1])
            vz = tz - float(surface.vertices[0][2])
            upd2["vertices"] = [(float(x) + vx, float(y) + vy, float(z) + vz) for x, y, z in surface.vertices]
        return ("surface", oid, upd2)

    if prefix == "opening":
        opening = next((o for o in project.geometry.openings if o.id == oid), None)
        if opening is None:
            raise ValueError(f"Unknown opening: {oid}")
        upd3: Dict[str, object] = {}
        if name:
            upd3["name"] = name
        if opening.vertices:
            vx = tx - float(opening.vertices[0][0])
            vy = ty - float(opening.vertices[0][1])
            vz = tz - float(opening.vertices[0][2])
            upd3["vertices"] = [(float(x) + vx, float(y) + vy, float(z) + vz) for x, y, z in opening.vertices]
        return ("opening", oid, upd3)

    if prefix == "luminaire":
        lum = next((l for l in project.luminaires if l.id == oid), None)
        if lum is None:
            raise ValueError(f"Unknown luminaire: {oid}")
        upd4: Dict[str, object] = {
            "transform": TransformSpec(
                position=(tx, ty, tz),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(yaw, pitch, roll)),
            )
        }
        if name:
            upd4["name"] = name
        return ("luminaire", oid, upd4)

    if prefix == "grid":
        grid = next((g for g in project.grids if g.id == oid), None)
        if grid is None:
            raise ValueError(f"Unknown grid: {oid}")
        upd5: Dict[str, object] = {"origin": (tx, ty, tz)}
        if name:
            upd5["name"] = name
        return ("grid", oid, upd5)

    if prefix == "level":
        level = next((l for l in project.geometry.levels if l.id == oid), None)
        if level is None:
            raise ValueError(f"Unknown level: {oid}")
        upd6: Dict[str, object] = {"elevation": tz}
        if name:
            upd6["name"] = name
        return ("level", oid, upd6)

    raise ValueError(f"Scene node type not editable: {prefix}")
