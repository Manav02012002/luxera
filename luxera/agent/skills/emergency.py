from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from luxera.gui.commands import cmd_add_emergency_job, cmd_add_escape_route
from luxera.project.diff import ProjectDiff
from luxera.project.io import load_project_schema


@dataclass(frozen=True)
class EmergencySkillOutput:
    plan: str
    diff: ProjectDiff
    run_manifest: Dict[str, object]


def build_emergency_skill(
    project_path: str,
    route_polyline: List[Tuple[float, float, float]],
    route_id: str = "route_1",
    standard: str = "EN1838",
    emergency_factor: float = 1.0,
) -> EmergencySkillOutput:
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    if not project.grids:
        raise ValueError("Emergency skill requires at least one open-area grid target")
    if not route_polyline or len(route_polyline) < 2:
        raise ValueError("Emergency skill requires a route polyline with at least two points")

    ops = []
    route_diff = cmd_add_escape_route(str(ppath), route_id=route_id, polyline=route_polyline, width_m=1.0, spacing_m=0.5)
    ops.extend(route_diff.ops)
    actual_route_id = route_diff.ops[0].id if route_diff.ops else route_id
    job_diff = cmd_add_emergency_job(
        str(ppath),
        routes=[actual_route_id],
        open_area_targets=[g.id for g in project.grids],
        standard=standard,
        emergency_factor=emergency_factor,
    )
    ops.extend(job_diff.ops)
    job_id = job_diff.ops[0].id if job_diff.ops else ""

    return EmergencySkillOutput(
        plan="Add escape route, create emergency job with route/open-area targets, then run and report.",
        diff=ProjectDiff(ops=ops),
        run_manifest={
            "skill": "emergency",
            "route_id": actual_route_id,
            "job_id": job_id,
            "standard": standard,
            "emergency_factor": emergency_factor,
        },
    )
