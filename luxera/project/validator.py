from __future__ import annotations

from typing import List, Set

from luxera.project.schema import JobSpec, Project


class ProjectValidationError(ValueError):
    pass


def _unique_ids(items, label: str) -> List[str]:
    seen: Set[str] = set()
    errors: List[str] = []
    for item in items:
        item_id = getattr(item, "id", None)
        if not item_id:
            errors.append(f"{label} has missing id")
            continue
        if item_id in seen:
            errors.append(f"Duplicate {label} id: {item_id}")
            continue
        seen.add(item_id)
    return errors


def _validate_project_schema(project: Project) -> List[str]:
    errors: List[str] = []

    errors.extend(_unique_ids(project.geometry.rooms, "room"))
    errors.extend(_unique_ids(project.geometry.zones, "zone"))
    errors.extend(_unique_ids(project.geometry.surfaces, "surface"))
    errors.extend(_unique_ids(project.geometry.openings, "opening"))
    errors.extend(_unique_ids(project.geometry.obstructions, "obstruction"))
    errors.extend(_unique_ids(project.geometry.levels, "level"))
    errors.extend(_unique_ids(project.geometry.coordinate_systems, "coordinate system"))
    errors.extend(_unique_ids(project.workplanes, "workplane"))
    errors.extend(_unique_ids(project.vertical_planes, "vertical plane"))
    errors.extend(_unique_ids(project.point_sets, "point set"))
    errors.extend(_unique_ids(project.glare_views, "glare view"))
    errors.extend(_unique_ids(project.roadway_grids, "roadway grid"))
    errors.extend(_unique_ids(project.compliance_profiles, "compliance profile"))
    errors.extend(_unique_ids(project.variants, "variant"))

    if project.geometry.length_unit not in {"m", "ft"}:
        errors.append(f"Unsupported geometry length unit: {project.geometry.length_unit}")

    room_ids = {r.id for r in project.geometry.rooms}
    zone_ids = {z.id for z in project.geometry.zones}
    surface_ids = {s.id for s in project.geometry.surfaces}
    level_ids = {lvl.id for lvl in project.geometry.levels}
    csys_ids = {cs.id for cs in project.geometry.coordinate_systems}

    for room in project.geometry.rooms:
        if room.level_id and room.level_id not in level_ids:
            errors.append(f"Room {room.id} references missing level {room.level_id}")
        if room.coordinate_system_id and room.coordinate_system_id not in csys_ids:
            errors.append(f"Room {room.id} references missing coordinate system {room.coordinate_system_id}")

    for zone in project.geometry.zones:
        for room_id in zone.room_ids:
            if room_id not in room_ids:
                errors.append(f"Zone {zone.id} references missing room {room_id}")

    for opening in project.geometry.openings:
        if opening.host_surface_id and opening.host_surface_id not in surface_ids:
            errors.append(f"Opening {opening.id} references missing host surface {opening.host_surface_id}")

    for profile in project.compliance_profiles:
        if not profile.thresholds:
            errors.append(f"Compliance profile {profile.id} has empty thresholds")

    variant_ids = {v.id for v in project.variants}
    if project.active_variant_id and project.active_variant_id not in variant_ids:
        errors.append(f"Active variant references missing id {project.active_variant_id}")

    for grid in project.grids:
        if project.geometry.rooms and not grid.room_id and not grid.zone_id:
            errors.append(f"Grid {grid.id} must reference room_id or zone_id when rooms exist")
        if grid.room_id and grid.room_id not in room_ids:
            errors.append(f"Grid {grid.id} references missing room {grid.room_id}")
        if grid.zone_id and grid.zone_id not in zone_ids:
            errors.append(f"Grid {grid.id} references missing zone {grid.zone_id}")

    for wp in project.workplanes:
        if not wp.room_id and not wp.zone_id:
            errors.append(f"Workplane {wp.id} must reference room_id or zone_id")
        if wp.room_id and wp.room_id not in room_ids:
            errors.append(f"Workplane {wp.id} references missing room {wp.room_id}")
        if wp.zone_id and wp.zone_id not in zone_ids:
            errors.append(f"Workplane {wp.id} references missing zone {wp.zone_id}")
        if wp.spacing <= 0:
            errors.append(f"Workplane {wp.id} spacing must be > 0")

    for vp in project.vertical_planes:
        if not vp.room_id and not vp.zone_id:
            errors.append(f"Vertical plane {vp.id} must reference room_id or zone_id")
        if vp.room_id and vp.room_id not in room_ids:
            errors.append(f"Vertical plane {vp.id} references missing room {vp.room_id}")
        if vp.zone_id and vp.zone_id not in zone_ids:
            errors.append(f"Vertical plane {vp.id} references missing zone {vp.zone_id}")
        if vp.width <= 0 or vp.height <= 0:
            errors.append(f"Vertical plane {vp.id} width/height must be > 0")
        if vp.nx <= 0 or vp.ny <= 0:
            errors.append(f"Vertical plane {vp.id} nx/ny must be > 0")

    for ps in project.point_sets:
        if not ps.room_id and not ps.zone_id:
            errors.append(f"Point set {ps.id} must reference room_id or zone_id")
        if ps.room_id and ps.room_id not in room_ids:
            errors.append(f"Point set {ps.id} references missing room {ps.room_id}")
        if ps.zone_id and ps.zone_id not in zone_ids:
            errors.append(f"Point set {ps.id} references missing zone {ps.zone_id}")
        if not ps.points:
            errors.append(f"Point set {ps.id} has no points")

    for gv in project.glare_views:
        if not gv.room_id and not gv.zone_id:
            errors.append(f"Glare view {gv.id} must reference room_id or zone_id")
        if gv.room_id and gv.room_id not in room_ids:
            errors.append(f"Glare view {gv.id} references missing room {gv.room_id}")
        if gv.zone_id and gv.zone_id not in zone_ids:
            errors.append(f"Glare view {gv.id} references missing zone {gv.zone_id}")

    for rg in project.roadway_grids:
        if rg.lane_width <= 0 or rg.road_length <= 0:
            errors.append(f"Roadway grid {rg.id} lane_width/road_length must be > 0")
        if rg.nx <= 0 or rg.ny <= 0:
            errors.append(f"Roadway grid {rg.id} nx/ny must be > 0")
        if getattr(rg, "num_lanes", 1) <= 0:
            errors.append(f"Roadway grid {rg.id} num_lanes must be > 0")
        if getattr(rg, "observer_height_m", 1.5) <= 0:
            errors.append(f"Roadway grid {rg.id} observer_height_m must be > 0")

    return errors


def validate_project_for_job(project: Project, job: JobSpec) -> None:
    """
    Validate project state before executing a job.

    This enforces deterministic/explicit inputs and blocks ambiguous runs.
    """
    errors: List[str] = _validate_project_schema(project)

    errors.extend(_unique_ids(project.photometry_assets, "photometry asset"))
    errors.extend(_unique_ids(project.luminaires, "luminaire"))
    errors.extend(_unique_ids(project.grids, "grid"))
    errors.extend(_unique_ids(project.jobs, "job"))

    supported_formats = {"IES", "LDT"}
    asset_ids = set()
    for asset in project.photometry_assets:
        asset_ids.add(asset.id)
        if asset.format not in supported_formats:
            errors.append(f"Unsupported photometry format for asset {asset.id}: {asset.format}")
        if not asset.path and not asset.embedded_b64:
            errors.append(f"Photometry asset {asset.id} has no path or embedded data")

    for lum in project.luminaires:
        if lum.photometry_asset_id not in asset_ids:
            errors.append(f"Luminaire {lum.id} references missing asset {lum.photometry_asset_id}")

    for grid in project.grids:
        if grid.width <= 0 or grid.height <= 0:
            errors.append(f"Grid {grid.id} width/height must be > 0")
        if grid.nx <= 0 or grid.ny <= 0:
            errors.append(f"Grid {grid.id} nx/ny must be > 0")

    for room in project.geometry.rooms:
        if room.width <= 0 or room.length <= 0 or room.height <= 0:
            errors.append(f"Room {room.id} dimensions must be > 0")

    if job.backend not in {"cpu", "radiance"}:
        errors.append(f"Unsupported backend: {job.backend}")

    if job.type == "direct":
        if not project.grids:
            errors.append("Direct job requires at least one grid")
        if not project.luminaires:
            errors.append("Direct job requires at least one luminaire")
    elif job.type == "radiosity":
        if not project.geometry.rooms:
            errors.append("Radiosity job requires at least one room")
        if not project.luminaires:
            errors.append("Radiosity job requires at least one luminaire")
    elif job.type == "roadway":
        if not project.roadway_grids:
            errors.append("Roadway job requires at least one roadway grid")
        if not project.luminaires:
            errors.append("Roadway job requires at least one luminaire")
    elif job.type == "emergency":
        if not project.grids:
            errors.append("Emergency job requires at least one grid")
        if not project.luminaires:
            errors.append("Emergency job requires at least one luminaire")
    elif job.type == "daylight":
        if not project.grids:
            errors.append("Daylight job requires at least one grid")
    else:
        errors.append(f"Unsupported job type: {job.type}")

    if errors:
        raise ProjectValidationError("Project/job validation failed:\n- " + "\n- ".join(errors))
