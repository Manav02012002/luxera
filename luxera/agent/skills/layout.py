from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from luxera.gui.commands import cmd_place_rect_array
from luxera.project.diff import ProjectDiff
from luxera.project.io import load_project_schema


@dataclass(frozen=True)
class LayoutSkillOutput:
    plan: str
    diff: ProjectDiff
    run_manifest: Dict[str, object]


def build_layout_skill(
    project_path: str,
    target_lux: float = 500.0,
    uniformity_min: float = 0.4,
    fixture_asset_id: str | None = None,
) -> LayoutSkillOutput:
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    if not project.geometry.rooms:
        raise ValueError("Layout skill requires at least one room")
    if not project.photometry_assets:
        raise ValueError("Layout skill requires at least one photometry asset")
    room = project.geometry.rooms[0]
    asset_id = fixture_asset_id or project.photometry_assets[0].id
    # Deterministic one-step heuristic.
    nx = 4 if target_lux >= 400 else 3
    ny = 3 if uniformity_min >= 0.4 else 2
    diff = cmd_place_rect_array(str(ppath), room.id, asset_id, nx=nx, ny=ny, margins=0.8, mount_height=room.height * 0.9)
    return LayoutSkillOutput(
        plan="Place deterministic rectangular luminaire array and refine for target illuminance.",
        diff=diff,
        run_manifest={"skill": "layout", "target_lux": target_lux, "uniformity_min": uniformity_min, "asset_id": asset_id},
    )
