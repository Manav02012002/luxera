from __future__ import annotations

from typing import Any, Dict, Optional

from luxera.agent.context import (
    CalcObjectContext,
    ConstraintContext,
    LuminaireContext,
    ProjectContext,
    RoomContext,
)
from luxera.project.schema import Project


def _latest_summary(project: Project) -> Dict[str, Any]:
    if not project.results:
        return {}
    return dict(project.results[-1].summary or {})


def _room_material_map(project: Project, room_id: str) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {"floor": None, "wall": None, "ceiling": None}
    for surface in project.geometry.surfaces:
        if surface.room_id != room_id:
            continue
        if surface.kind in out and out[surface.kind] is None:
            out[surface.kind] = surface.material_id
    return out


def _calc_pass_fail(calc_id: str, summary: Dict[str, Any]) -> Optional[str]:
    compliance = summary.get("compliance")
    if isinstance(compliance, dict):
        v = compliance.get(calc_id)
        if isinstance(v, bool):
            return "pass" if v else "fail"
        if isinstance(v, str):
            return v.lower()
    if isinstance(compliance, str):
        txt = compliance.strip().lower()
        if "pass" in txt:
            return "pass"
        if "non-compliant" in txt or "fail" in txt:
            return "fail"
    return None


def _extract_constraints(project: Project) -> ConstraintContext:
    source: Dict[str, Any] = {}
    if project.jobs:
        source.update(project.jobs[0].settings or {})
    if project.compliance_profiles:
        source.update(project.compliance_profiles[0].thresholds or {})
    return ConstraintContext(
        target_lux=_to_float(source.get("target_lux") or source.get("e_avg_min")),
        uniformity_min=_to_float(source.get("uniformity_min") or source.get("u0_min")),
        ugr_max=_to_float(source.get("ugr_max")),
        max_fittings=_to_int(source.get("max_fittings") or source.get("max_count")),
        max_spacing_m=_to_float(source.get("max_spacing_m")),
        budget=_to_float(source.get("budget")),
    )


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def summarize_project(project: Project) -> ProjectContext:
    summary = _latest_summary(project)
    rooms = [
        RoomContext(
            id=room.id,
            name=room.name,
            dims_m={"width": float(room.width), "length": float(room.length), "height": float(room.height)},
            materials=_room_material_map(project, room.id),
        )
        for room in project.geometry.rooms
    ]
    luminaires = [
        LuminaireContext(
            id=lum.id,
            name=lum.name,
            photometry_asset_id=lum.photometry_asset_id,
            mounting_height_m=lum.mounting_height_m,
            tilt_deg=float(lum.tilt_deg),
        )
        for lum in project.luminaires
    ]
    calc_objects = []
    for grid in project.grids:
        calc_objects.append(
            CalcObjectContext(
                id=grid.id,
                kind="HorizontalGrid",
                metric_set=list(grid.metric_set),
                pass_fail=_calc_pass_fail(grid.id, summary),
            )
        )
    for plane in project.vertical_planes:
        calc_objects.append(
            CalcObjectContext(
                id=plane.id,
                kind="VerticalGrid",
                metric_set=list(plane.metric_set),
                pass_fail=_calc_pass_fail(plane.id, summary),
            )
        )
    for plane in project.arbitrary_planes:
        calc_objects.append(
            CalcObjectContext(
                id=plane.id,
                kind="ArbitraryPlaneGrid",
                metric_set=list(plane.metric_set),
                pass_fail=_calc_pass_fail(plane.id, summary),
            )
        )
    for point_set in project.point_sets:
        calc_objects.append(
            CalcObjectContext(
                id=point_set.id,
                kind="PointSet",
                metric_set=list(point_set.metric_set),
                pass_fail=_calc_pass_fail(point_set.id, summary),
            )
        )
    for line_grid in project.line_grids:
        calc_objects.append(
            CalcObjectContext(
                id=line_grid.id,
                kind="LineGrid",
                metric_set=list(line_grid.metric_set),
                pass_fail=_calc_pass_fail(line_grid.id, summary),
            )
        )
    for glare in project.glare_views:
        calc_objects.append(CalcObjectContext(id=glare.id, kind="UGRView", metric_set=["UGR"], pass_fail=_calc_pass_fail(glare.id, summary)))
    for roadway in project.roadway_grids:
        calc_objects.append(
            CalcObjectContext(
                id=roadway.id,
                kind="RoadwayGrid",
                metric_set=list(roadway.metric_set),
                pass_fail=_calc_pass_fail(roadway.id, summary),
            )
        )
    return ProjectContext(
        project_name=project.name,
        rooms=rooms,
        luminaires=luminaires,
        calc_objects=calc_objects,
        constraints=_extract_constraints(project),
        latest_summary=summary,
    )
