from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any, Dict

from luxera.project.schema import Project


def push_snapshot(project: Project, label: str = "assistant_change") -> None:
    snap = asdict(project)
    snap["label"] = label
    project.assistant_undo_stack.append(snap)
    project.assistant_redo_stack = []


def _restore(project: Project, snap: Dict[str, Any]) -> None:
    from luxera.project.io import _project_from_dict  # type: ignore[attr-defined]

    restored = _project_from_dict({k: deepcopy(v) for k, v in snap.items() if k != "label"})
    project.geometry = restored.geometry
    project.materials = restored.materials
    project.material_library = restored.material_library
    project.photometry_assets = restored.photometry_assets
    project.luminaire_families = restored.luminaire_families
    project.luminaires = restored.luminaires
    project.grids = restored.grids
    project.workplanes = restored.workplanes
    project.vertical_planes = restored.vertical_planes
    project.point_sets = restored.point_sets
    project.glare_views = restored.glare_views
    project.roadways = restored.roadways
    project.roadway_grids = restored.roadway_grids
    project.compliance_profiles = restored.compliance_profiles
    project.variants = restored.variants
    project.active_variant_id = restored.active_variant_id
    project.jobs = restored.jobs
    project.results = restored.results


def undo(project: Project) -> bool:
    if not project.assistant_undo_stack:
        return False
    current = asdict(project)
    current["label"] = "redo_snapshot"
    snap = project.assistant_undo_stack.pop()
    project.assistant_redo_stack.append(current)
    _restore(project, snap)
    return True


def redo(project: Project) -> bool:
    if not project.assistant_redo_stack:
        return False
    current = asdict(project)
    current["label"] = "undo_snapshot"
    snap = project.assistant_redo_stack.pop()
    project.assistant_undo_stack.append(current)
    _restore(project, snap)
    return True
