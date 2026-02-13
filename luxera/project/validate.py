"""Contract: docs/spec/validation_policy.md, docs/spec/daylight_contract.md, docs/spec/emergency_contract.md."""

from __future__ import annotations

from typing import List

from luxera.backends.radiance import detect_radiance_tools
from luxera.project.validator import ProjectValidationError, validate_project_for_job
from luxera.project.schema import JobSpec, Project


def validate_daylight(project: Project, job: JobSpec) -> None:
    if job.type != "daylight":
        raise ProjectValidationError(f"validate_daylight called for non-daylight job: {job.id}")
    errors: List[str] = []

    apertures = [o for o in project.geometry.openings if bool(getattr(o, "is_daylight_aperture", False))]
    if not apertures:
        errors.append("Daylight job requires at least one daylight aperture (OpeningSpec.is_daylight_aperture=true)")

    ds = job.daylight
    default_vt = float(ds.glass_visible_transmittance_default) if ds is not None else 0.70
    if default_vt <= 0.0 or default_vt > 1.0:
        errors.append("DaylightSpec.glass_visible_transmittance_default must be in (0,1]")
    for op in apertures:
        vt = op.vt if op.vt is not None else op.visible_transmittance
        vt = vt if vt is not None else default_vt
        if vt is None or float(vt) <= 0.0 or float(vt) > 1.0:
            errors.append(f"Aperture {op.id} has invalid visible_transmittance: {vt}")

    mode = (ds.mode if ds is not None else "df").lower()
    e0 = ds.external_horizontal_illuminance_lux if ds is not None else None
    if mode == "df":
        if e0 is None or float(e0) <= 0.0:
            errors.append("Daylight DF mode requires external_horizontal_illuminance_lux > 0")
    elif mode == "radiance":
        tools = detect_radiance_tools()
        if not tools.available:
            errors.append(f"Daylight Radiance mode requires Radiance tools; missing: {', '.join(tools.missing)}")
    elif mode == "annual":
        tools = detect_radiance_tools()
        if not tools.available:
            errors.append(f"Daylight annual mode requires Radiance tools; missing: {', '.join(tools.missing)}")
        annual = ds.annual if ds is not None else None
        if annual is None:
            errors.append("Daylight annual mode requires DaylightSpec.annual configuration")
        else:
            if str(annual.annual_method_preference) not in {"matrix", "hourly_rtrace", "auto"}:
                errors.append("Daylight annual annual_method_preference must be one of: matrix, hourly_rtrace, auto")
            if not annual.weather_file:
                errors.append("Daylight annual mode requires DaylightAnnualSpec.weather_file")
            elif project.root_dir:
                from pathlib import Path

                p = Path(annual.weather_file).expanduser()
                if not p.is_absolute():
                    p = Path(project.root_dir).expanduser().resolve() / p
                if not p.exists():
                    errors.append(f"Daylight annual weather file not found: {p}")
            if annual.sda_target_lux <= 0.0:
                errors.append("Daylight annual sda_target_lux must be > 0")
            if annual.ase_threshold_lux <= 0.0:
                errors.append("Daylight annual ase_threshold_lux must be > 0")
            if annual.udi_low <= 0.0 or annual.udi_high <= annual.udi_low:
                errors.append("Daylight annual UDI range must satisfy 0 < udi_low < udi_high")
    else:
        errors.append(f"Unsupported daylight mode: {mode}")

    target_ids = set(job.targets) if job.targets else {g.id for g in project.grids}
    if not target_ids:
        errors.append("Daylight job requires explicit targets or at least one grid")
    valid_ids = {g.id for g in project.grids} | {vp.id for vp in project.vertical_planes} | {ps.id for ps in project.point_sets}
    missing_targets = sorted(t for t in target_ids if t not in valid_ids)
    if missing_targets:
        errors.append(f"Daylight targets not found: {missing_targets}")

    if errors:
        raise ProjectValidationError("Daylight validation failed:\n- " + "\n- ".join(errors))


def validate_emergency(project: Project, job: JobSpec) -> None:
    if job.type != "emergency":
        raise ProjectValidationError(f"validate_emergency called for non-emergency job: {job.id}")
    errors: List[str] = []

    route_ids = set(job.routes or [])
    if route_ids:
        routes = {r.id: r for r in project.escape_routes}
        for rid in sorted(route_ids):
            route = routes.get(rid)
            if route is None:
                errors.append(f"Emergency route not found: {rid}")
                continue
            if len(route.polyline) < 2:
                errors.append(f"Escape route {rid} must have at least 2 polyline points")
            if route.width_m <= 0.0:
                errors.append(f"Escape route {rid} width_m must be > 0")
            if route.spacing_m <= 0.0:
                errors.append(f"Escape route {rid} spacing_m must be > 0")

    if job.open_area_targets:
        valid_grid_ids = {g.id for g in project.grids}
        missing = sorted(t for t in job.open_area_targets if t not in valid_grid_ids)
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

    if errors:
        raise ProjectValidationError("Emergency validation failed:\n- " + "\n- ".join(errors))


__all__ = [
    "ProjectValidationError",
    "validate_project_for_job",
    "validate_daylight",
    "validate_emergency",
]
