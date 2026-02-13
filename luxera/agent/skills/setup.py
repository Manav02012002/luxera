from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from luxera.gui.commands import cmd_add_workplane_grid, cmd_detect_rooms, cmd_import_geometry
from luxera.project.diff import DiffOp, ProjectDiff
from luxera.project.io import load_project_schema
from luxera.project.schema import JobSpec


@dataclass(frozen=True)
class SetupSkillOutput:
    plan: str
    diff: ProjectDiff
    run_manifest: Dict[str, object]


def build_setup_skill(
    project_path: str,
    geometry_file: Optional[str] = None,
    room_type: str = "office",
) -> SetupSkillOutput:
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    ops = []
    if geometry_file:
        ops.extend(cmd_import_geometry(str(ppath), geometry_file).ops)
    ops.extend(cmd_detect_rooms(str(ppath)).ops)

    for room in project.geometry.rooms:
        ops.append(DiffOp(op="update", kind="room", id=room.id, payload={"activity_type": "OFFICE_GENERAL"}))
    if project.geometry.rooms:
        room = project.geometry.rooms[0]
        ops.extend(cmd_add_workplane_grid(str(ppath), room.id, height=0.8, spacing=0.25, margins=0.0).ops)

    if not any(j.type == "direct" for j in project.jobs):
        job_id = f"{room_type}_direct"
        ops.append(
            DiffOp(
                op="add",
                kind="job",
                id=job_id,
                payload=JobSpec(id=job_id, type="direct", backend="cpu", settings={"use_occlusion": False}, seed=0),
            )
        )

    plan = "Import geometry, detect rooms, assign defaults, create workplane grid, and add direct job."
    return SetupSkillOutput(
        plan=plan,
        diff=ProjectDiff(ops=ops),
        run_manifest={"skill": "setup", "room_type": room_type, "geometry_file": geometry_file},
    )
