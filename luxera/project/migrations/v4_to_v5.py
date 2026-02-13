from __future__ import annotations

from typing import Dict, Any


def _unit_scale_to_m(unit: str) -> float:
    u = str(unit).lower()
    if u == "m":
        return 1.0
    if u == "mm":
        return 0.001
    if u == "cm":
        return 0.01
    if u == "ft":
        return 0.3048
    if u == "in":
        return 0.0254
    return 1.0


def _normalize_unit(unit: str) -> str:
    u = str(unit).lower()
    if u in {"m", "meter", "meters"}:
        return "m"
    if u in {"mm", "millimeter", "millimeters"}:
        return "mm"
    if u in {"cm", "centimeter", "centimeters"}:
        return "cm"
    if u in {"ft", "feet", "foot"}:
        return "ft"
    if u in {"in", "inch", "inches"}:
        return "in"
    return "m"


def migrate(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("schema_version", 4) != 4:
        return data

    geometry = data.setdefault("geometry", {})
    geometry.setdefault("zones", [])
    geometry.setdefault("no_go_zones", [])
    geometry.setdefault("surfaces", [])
    geometry.setdefault("openings", [])
    geometry.setdefault("obstructions", [])
    geometry.setdefault("levels", [])
    geometry.setdefault("coordinate_systems", [])
    geometry.setdefault("length_unit", "m")
    geometry.setdefault("scale_to_meters", _unit_scale_to_m(geometry.get("length_unit", "m")))

    for room in geometry.get("rooms", []):
        room.setdefault("level_id", None)
        room.setdefault("coordinate_system_id", None)
    for cs in geometry.get("coordinate_systems", []):
        unit = _normalize_unit(cs.get("length_unit", cs.get("units", "m")))
        cs.setdefault("units", unit)
        cs.setdefault("length_unit", unit)
        cs.setdefault("scale_to_meters", _unit_scale_to_m(unit))

    for material in data.get("materials", []):
        material.setdefault("reflectance_rgb", None)
        material.setdefault("maintenance_factor_placeholder", None)

    for lum in data.get("luminaires", []):
        lum.setdefault("mounting_type", None)
        lum.setdefault("mounting_height_m", None)

    for grid in data.get("grids", []):
        grid.setdefault("room_id", None)
        grid.setdefault("zone_id", None)

    data.setdefault("workplanes", [])
    data.setdefault("vertical_planes", [])
    data.setdefault("point_sets", [])
    data.setdefault("glare_views", [])
    data.setdefault("roadways", [])
    data.setdefault("roadway_grids", [])
    data.setdefault("compliance_profiles", [])
    data.setdefault("variants", [])
    data.setdefault("active_variant_id", None)
    data.setdefault("assistant_undo_stack", [])
    data.setdefault("assistant_redo_stack", [])

    data["schema_version"] = 5
    return data
