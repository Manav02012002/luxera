from __future__ import annotations
"""Contract: docs/spec/validation_policy.md, docs/spec/photometry_contracts.md."""

from pathlib import Path
from typing import List, Set

from luxera.backends.radiance import detect_radiance_tools
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.tilt_file import load_tilt_file
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
    errors.extend(_unique_ids(project.geometry.no_go_zones, "no-go zone"))
    errors.extend(_unique_ids(project.geometry.surfaces, "surface"))
    errors.extend(_unique_ids(project.geometry.openings, "opening"))
    errors.extend(_unique_ids(project.geometry.obstructions, "obstruction"))
    errors.extend(_unique_ids(project.geometry.levels, "level"))
    errors.extend(_unique_ids(project.geometry.coordinate_systems, "coordinate system"))
    errors.extend(_unique_ids(project.workplanes, "workplane"))
    errors.extend(_unique_ids(project.vertical_planes, "vertical plane"))
    errors.extend(_unique_ids(project.arbitrary_planes, "arbitrary plane"))
    errors.extend(_unique_ids(project.point_sets, "point set"))
    errors.extend(_unique_ids(project.line_grids, "line grid"))
    errors.extend(_unique_ids(project.glare_views, "glare view"))
    errors.extend(_unique_ids(project.roadways, "roadway"))
    errors.extend(_unique_ids(project.roadway_grids, "roadway grid"))
    errors.extend(_unique_ids(project.compliance_profiles, "compliance profile"))
    errors.extend(_unique_ids(project.variants, "variant"))

    if project.geometry.length_unit not in {"m", "mm", "cm", "ft", "in"}:
        errors.append(f"Unsupported geometry length unit: {project.geometry.length_unit}")
    if getattr(project.geometry, "scale_to_meters", 0.0) <= 0.0:
        errors.append("Geometry scale_to_meters must be > 0")

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
    for cs in project.geometry.coordinate_systems:
        if cs.length_unit not in {"m", "mm", "cm", "ft", "in"}:
            errors.append(f"Coordinate system {cs.id} has unsupported length unit: {cs.length_unit}")
        if float(getattr(cs, "scale_to_meters", 0.0) or 0.0) <= 0.0:
            errors.append(f"Coordinate system {cs.id} scale_to_meters must be > 0")

    for zone in project.geometry.zones:
        for room_id in zone.room_ids:
            if room_id not in room_ids:
                errors.append(f"Zone {zone.id} references missing room {room_id}")

    for ng in project.geometry.no_go_zones:
        if ng.room_id and ng.room_id not in room_ids:
            errors.append(f"No-go zone {ng.id} references missing room {ng.room_id}")
        if len(ng.vertices) < 3:
            errors.append(f"No-go zone {ng.id} must have at least 3 vertices")

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
        host_surface_id = getattr(vp, "host_surface_id", None)
        if not vp.room_id and not vp.zone_id and not host_surface_id:
            errors.append(f"Vertical plane {vp.id} must reference room_id, zone_id, or host_surface_id")
        if vp.room_id and vp.room_id not in room_ids:
            errors.append(f"Vertical plane {vp.id} references missing room {vp.room_id}")
        if vp.zone_id and vp.zone_id not in zone_ids:
            errors.append(f"Vertical plane {vp.id} references missing zone {vp.zone_id}")
        if host_surface_id:
            if not any(s.id == host_surface_id for s in project.geometry.surfaces):
                errors.append(f"Vertical plane {vp.id} references missing host surface {host_surface_id}")
        if vp.width <= 0 or vp.height <= 0:
            errors.append(f"Vertical plane {vp.id} width/height must be > 0")
        if vp.nx <= 0 or vp.ny <= 0:
            errors.append(f"Vertical plane {vp.id} nx/ny must be > 0")

    for ap in project.arbitrary_planes:
        if not ap.room_id and not ap.zone_id:
            errors.append(f"Arbitrary plane {ap.id} must reference room_id or zone_id")
        if ap.room_id and ap.room_id not in room_ids:
            errors.append(f"Arbitrary plane {ap.id} references missing room {ap.room_id}")
        if ap.zone_id and ap.zone_id not in zone_ids:
            errors.append(f"Arbitrary plane {ap.id} references missing zone {ap.zone_id}")
        if ap.width <= 0 or ap.height <= 0:
            errors.append(f"Arbitrary plane {ap.id} width/height must be > 0")
        if ap.nx <= 0 or ap.ny <= 0:
            errors.append(f"Arbitrary plane {ap.id} nx/ny must be > 0")

    for ps in project.point_sets:
        if not ps.room_id and not ps.zone_id:
            errors.append(f"Point set {ps.id} must reference room_id or zone_id")
        if ps.room_id and ps.room_id not in room_ids:
            errors.append(f"Point set {ps.id} references missing room {ps.room_id}")
        if ps.zone_id and ps.zone_id not in zone_ids:
            errors.append(f"Point set {ps.id} references missing zone {ps.zone_id}")
        if not ps.points:
            errors.append(f"Point set {ps.id} has no points")

    for lg in project.line_grids:
        if not lg.room_id and not lg.zone_id:
            errors.append(f"Line grid {lg.id} must reference room_id or zone_id")
        if lg.room_id and lg.room_id not in room_ids:
            errors.append(f"Line grid {lg.id} references missing room {lg.room_id}")
        if lg.zone_id and lg.zone_id not in zone_ids:
            errors.append(f"Line grid {lg.id} references missing zone {lg.zone_id}")
        if len(lg.polyline) < 2:
            errors.append(f"Line grid {lg.id} must have at least 2 polyline points")
        if float(lg.spacing) <= 0.0:
            errors.append(f"Line grid {lg.id} spacing must be > 0")

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
        if getattr(rg, "roadway_id", None):
            if not any(rw.id == rg.roadway_id for rw in project.roadways):
                errors.append(f"Roadway grid {rg.id} references missing roadway {rg.roadway_id}")

    for rw in project.roadways:
        if rw.num_lanes <= 0:
            errors.append(f"Roadway {rw.id} num_lanes must be > 0")
        if rw.lane_width <= 0:
            errors.append(f"Roadway {rw.id} lane_width must be > 0")
        if tuple(rw.start) == tuple(rw.end):
            errors.append(f"Roadway {rw.id} start/end must not be identical")

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
        if asset.format == "IES" and asset.path:
            try:
                apath = Path(asset.path).expanduser()
                if not apath.is_absolute() and project.root_dir:
                    apath = (Path(project.root_dir).expanduser() / apath).resolve()
                doc = parse_ies_text(apath.read_text(encoding="utf-8", errors="replace"), source_path=apath)
                if doc.photometry is not None and int(doc.photometry.photometric_type) != 1:
                    ptype = int(doc.photometry.photometric_type)
                    ptype_name = {1: "C", 2: "B", 3: "A"}.get(ptype, "UNKNOWN")
                    errors.append(
                        (
                            f"Unsupported photometric type in asset {asset.id} ({apath.name}): "
                            f"type={ptype} ({ptype_name}). Supported type is C only. "
                            "Convert file to Type C or choose a Type C asset."
                        )
                    )
                tilt_status = "ok"
                if (doc.tilt_mode or "").upper().startswith("FILE"):
                    if not doc.tilt_file_path:
                        tilt_status = "missing"
                        errors.append(f"Asset {asset.id} tilt_status={tilt_status}: TILT=FILE missing file reference")
                    else:
                        tpath = Path(doc.tilt_file_path).expanduser()
                        if not tpath.is_absolute():
                            tpath = (apath.parent / tpath).resolve()
                        if not tpath.exists():
                            tilt_status = "missing"
                            errors.append(
                                f"Asset {asset.id} tilt_status={tilt_status}: TILT=FILE target not found ({tpath})"
                            )
                        else:
                            try:
                                _ = load_tilt_file(tpath)
                            except Exception as te:
                                tilt_status = "failed"
                                errors.append(
                                    f"Asset {asset.id} tilt_status={tilt_status}: TILT=FILE parse failed ({te})"
                                )
            except Exception as e:
                errors.append(f"Failed to inspect IES photometric type for asset {asset.id}: {e}")

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

    for material in project.materials:
        if not (0.0 <= float(material.reflectance) <= 1.0):
            errors.append(f"Material {material.id} reflectance must be in [0,1]")
        if not (0.0 <= float(material.specularity) <= 1.0):
            errors.append(f"Material {material.id} specularity must be in [0,1]")
        if not (0.0 <= float(getattr(material, "transmittance", 0.0)) <= 1.0):
            errors.append(f"Material {material.id} transmittance must be in [0,1]")
        if getattr(material, "specular_reflectance", None) is not None:
            if not (0.0 <= float(material.specular_reflectance) <= 1.0):
                errors.append(f"Material {material.id} specular_reflectance must be in [0,1]")
        if getattr(material, "roughness", None) is not None:
            if not (0.0 <= float(material.roughness) <= 1.0):
                errors.append(f"Material {material.id} roughness must be in [0,1]")
        rgb = getattr(material, "diffuse_reflectance_rgb", None) or getattr(material, "reflectance_rgb", None)
        if rgb is not None:
            if len(rgb) != 3 or any((float(v) < 0.0 or float(v) > 1.0) for v in rgb):
                errors.append(f"Material {material.id} diffuse_reflectance_rgb must be 3 values in [0,1]")

    if job.backend not in {"cpu", "df", "radiance"}:
        errors.append(f"Unsupported backend: {job.backend}")

    if job.type == "direct":
        if not (project.grids or project.vertical_planes or project.arbitrary_planes or project.point_sets or project.line_grids):
            errors.append("Direct job requires at least one calculation object (grid, vertical plane, or point set)")
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
        route_ids = set(job.routes or [])
        if route_ids:
            routes = {r.id: r for r in project.escape_routes}
            for rid in sorted(route_ids):
                r = routes.get(rid)
                if r is None:
                    errors.append(f"Emergency route not found: {rid}")
                    continue
                if len(r.polyline) < 2:
                    errors.append(f"Escape route {rid} must have at least 2 polyline points")
                if float(r.width_m) <= 0.0:
                    errors.append(f"Escape route {rid} width_m must be > 0")
                if float(r.spacing_m) <= 0.0:
                    errors.append(f"Escape route {rid} spacing_m must be > 0")
        if job.open_area_targets:
            grid_ids = {g.id for g in project.grids}
            missing = sorted(t for t in job.open_area_targets if t not in grid_ids)
            if missing:
                errors.append(f"Emergency open-area targets not found: {missing}")
        include = set(job.mode.include_luminaires) if job.mode is not None else set()
        include = include | (set(job.mode.include_luminaire_ids) if job.mode is not None else set())
        include_tags = set(job.mode.include_tags) if job.mode is not None else set()
        if job.mode is not None and job.mode.include_tag:
            include_tags.add(str(job.mode.include_tag))
        exclude = set(job.mode.exclude_luminaires) if job.mode is not None else set()
        if include:
            lum_ids = {l.id for l in project.luminaires}
            unresolved = sorted(x for x in include if x not in lum_ids)
            if unresolved:
                errors.append(f"Emergency include_luminaires not found: {unresolved}")
        if include and include.issubset(exclude):
            errors.append("Emergency luminaire selection resolves to empty set")
        if include_tags:
            lum_tags = {l.id: set(getattr(l, "tags", []) or []) for l in project.luminaires}
            tagged = {lid for lid, tags in lum_tags.items() if tags.intersection(include_tags)}
            if not tagged:
                errors.append(f"Emergency include_tags resolves to empty set: {sorted(include_tags)}")
    elif job.type == "daylight":
        target_ids = set(job.targets) if job.targets else {g.id for g in project.grids}
        if not target_ids:
            errors.append("Daylight job requires at least one grid")
            errors.append("Daylight job requires explicit targets or at least one grid")
        valid_ids = {g.id for g in project.grids} | {vp.id for vp in project.vertical_planes} | {ps.id for ps in project.point_sets}
        missing_targets = sorted(t for t in target_ids if t not in valid_ids)
        if missing_targets:
            errors.append(f"Daylight targets not found: {missing_targets}")

        apertures = [o for o in project.geometry.openings if bool(getattr(o, "is_daylight_aperture", False))]
        if not apertures:
            errors.append("Daylight job requires at least one daylight aperture (OpeningSpec.is_daylight_aperture=true)")
        ds = job.daylight
        default_vt = float(ds.glass_visible_transmittance_default) if ds is not None else 0.70
        for op in apertures:
            vt = op.vt if op.vt is not None else op.visible_transmittance
            vt = vt if vt is not None else default_vt
            if vt is None or float(vt) <= 0.0 or float(vt) > 1.0:
                errors.append(f"Aperture {op.id} has invalid visible_transmittance: {vt}")
        mode = (ds.mode if ds is not None else ("df" if job.backend == "df" else "radiance" if job.backend == "radiance" else "df")).lower()
        if mode == "df":
            eo = ds.external_horizontal_illuminance_lux if ds is not None else None
            if eo is None or float(eo) <= 0.0:
                errors.append("Daylight DF mode requires external_horizontal_illuminance_lux > 0")
        elif mode == "radiance":
            tools = detect_radiance_tools()
            if not tools.available:
                errors.append(f"Daylight Radiance mode requires tools; missing: {', '.join(tools.missing)}")
        elif mode == "annual":
            tools = detect_radiance_tools()
            if not tools.available:
                errors.append(f"Daylight annual mode requires tools; missing: {', '.join(tools.missing)}")
            annual = ds.annual if ds is not None else None
            if annual is None:
                errors.append("Daylight annual mode requires DaylightSpec.annual")
            else:
                if str(annual.annual_method_preference) not in {"matrix", "hourly_rtrace", "auto"}:
                    errors.append("Daylight annual annual_method_preference must be one of: matrix, hourly_rtrace, auto")
                if not annual.weather_file:
                    errors.append("Daylight annual mode requires weather_file")
                else:
                    p = Path(annual.weather_file).expanduser()
                    if not p.is_absolute() and project.root_dir:
                        p = (Path(project.root_dir).expanduser() / p).resolve()
                    if not p.exists():
                        errors.append(f"Daylight annual weather file not found: {p}")
        else:
            errors.append(f"Unsupported daylight mode: {mode}")
    else:
        errors.append(f"Unsupported job type: {job.type}")

    if errors:
        raise ProjectValidationError("Project/job validation failed:\n- " + "\n- ".join(errors))
