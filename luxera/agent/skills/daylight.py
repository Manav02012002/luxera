from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from luxera.gui.commands import cmd_add_daylight_job, cmd_mark_opening_as_aperture
from luxera.project.diff import ProjectDiff
from luxera.project.io import load_project_schema


@dataclass(frozen=True)
class DaylightSkillOutput:
    plan: str
    diff: ProjectDiff
    run_manifest: Dict[str, object]


def build_daylight_skill(
    project_path: str,
    mode: str = "df",
    sky: str = "CIE_overcast",
    e0: float = 10000.0,
    vt: float = 0.70,
) -> DaylightSkillOutput:
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    targets: List[str] = [g.id for g in project.grids]
    if not targets:
        raise ValueError("Daylight skill requires at least one grid target")

    ops = []
    if project.geometry.openings:
        op = project.geometry.openings[0]
        ops.extend(cmd_mark_opening_as_aperture(str(ppath), opening_id=op.id, vt=vt).ops)
        aperture_id = op.id
    else:
        raise ValueError("Daylight skill requires at least one opening to mark as aperture")

    job_diff = cmd_add_daylight_job(str(ppath), targets=targets, mode=mode, sky=sky, e0=e0, vt=vt)
    ops.extend(job_diff.ops)
    job_id = job_diff.ops[0].id if job_diff.ops else ""

    return DaylightSkillOutput(
        plan="Mark daylight aperture(s), add daylight job for selected targets, then run/report.",
        diff=ProjectDiff(ops=ops),
        run_manifest={
            "skill": "daylight",
            "mode": mode,
            "sky": sky,
            "external_horizontal_illuminance_lux": e0,
            "visible_transmittance": vt,
            "targets": targets,
            "aperture_id": aperture_id,
            "job_id": job_id,
        },
    )
