from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from luxera.project.schema import Project


@dataclass
class ControlGroup:
    id: str
    name: str
    luminaire_ids: List[str]
    default_dimming: float = 1.0


@dataclass
class LightScene:
    id: str
    name: str
    description: str
    dimming_overrides: Dict[str, float]


class SceneManager:
    """Manages control groups and light scenes for a project."""

    def __init__(self, project: Project):
        self._project = project
        self._groups: Dict[str, ControlGroup] = {}
        self._scenes: Dict[str, LightScene] = {}

        for raw in project.control_groups:
            if not isinstance(raw, dict):
                continue
            group = ControlGroup(
                id=str(raw.get("id", "")),
                name=str(raw.get("name", "")),
                luminaire_ids=[str(x) for x in raw.get("luminaire_ids", []) if str(x)],
                default_dimming=float(raw.get("default_dimming", 1.0)),
            )
            if group.id:
                self._groups[group.id] = group
        for raw in project.light_scenes:
            if not isinstance(raw, dict):
                continue
            scene = LightScene(
                id=str(raw.get("id", "")),
                name=str(raw.get("name", "")),
                description=str(raw.get("description", "")),
                dimming_overrides={
                    str(k): float(v)
                    for k, v in dict(raw.get("dimming_overrides", {})).items()
                    if str(k)
                },
            )
            if scene.id:
                self._scenes[scene.id] = scene

        self._sync_project()

    @staticmethod
    def _clamp_dimming(v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    def _sync_project(self) -> None:
        self._project.control_groups = [asdict(g) for g in self._groups.values()]
        self._project.light_scenes = [asdict(s) for s in self._scenes.values()]

    def add_group(self, group: ControlGroup):
        """Add a control group. Validate all luminaire_ids exist in project."""
        if not group.id:
            raise ValueError("ControlGroup.id is required")
        known_ids = {str(l.id) for l in self._project.luminaires}
        missing = [lid for lid in group.luminaire_ids if lid not in known_ids]
        if missing:
            raise ValueError(f"Unknown luminaire ids in group {group.id}: {', '.join(missing)}")
        self._groups[group.id] = ControlGroup(
            id=group.id,
            name=group.name,
            luminaire_ids=[str(x) for x in group.luminaire_ids],
            default_dimming=self._clamp_dimming(group.default_dimming),
        )
        self._sync_project()

    def remove_group(self, group_id: str):
        """Remove group and clean up references in all scenes."""
        self._groups.pop(group_id, None)
        for sid, scene in list(self._scenes.items()):
            if group_id in scene.dimming_overrides:
                overrides = dict(scene.dimming_overrides)
                overrides.pop(group_id, None)
                self._scenes[sid] = LightScene(
                    id=scene.id,
                    name=scene.name,
                    description=scene.description,
                    dimming_overrides=overrides,
                )
        self._sync_project()

    def add_scene(self, scene: LightScene):
        """Add a light scene. Validate all group IDs in overrides exist."""
        if not scene.id:
            raise ValueError("LightScene.id is required")
        unknown = [gid for gid in scene.dimming_overrides.keys() if gid not in self._groups]
        if unknown:
            raise ValueError(f"Unknown control group ids in scene {scene.id}: {', '.join(unknown)}")
        self._scenes[scene.id] = LightScene(
            id=scene.id,
            name=scene.name,
            description=scene.description,
            dimming_overrides={k: self._clamp_dimming(v) for k, v in scene.dimming_overrides.items()},
        )
        self._sync_project()

    def remove_scene(self, scene_id: str):
        self._scenes.pop(scene_id, None)
        self._sync_project()

    def get_effective_dimming(self, scene_id: str) -> Dict[str, float]:
        """
        Return luminaire_id -> effective_dimming for a scene.
        Luminaires not in any group get dimming=1.0.
        Groups not overridden in the scene get their default_dimming.
        """
        scene = self._scenes.get(scene_id)
        if scene is None:
            raise ValueError(f"Unknown scene id: {scene_id}")
        dims: Dict[str, float] = {str(l.id): 1.0 for l in self._project.luminaires}
        assigned: set[str] = set()
        for gid, group in self._groups.items():
            d = self._clamp_dimming(scene.dimming_overrides.get(gid, group.default_dimming))
            for lum_id in group.luminaire_ids:
                dims[lum_id] = d
                assigned.add(lum_id)
        for lum in self._project.luminaires:
            if str(lum.id) not in assigned:
                dims[str(lum.id)] = 1.0
        return dims

    def apply_scene_to_project(self, scene_id: str) -> Project:
        """
        Return a copy of the project with luminaire flux_multipliers
        adjusted by the scene's dimming levels.
        """
        dims = self.get_effective_dimming(scene_id)
        out = copy.deepcopy(self._project)
        for lum in out.luminaires:
            d = dims.get(str(lum.id), 1.0)
            lum.flux_multiplier = float(lum.flux_multiplier) * float(d)
        return out

    def run_all_scenes(self, runner_fn, base_project: Project) -> Dict[str, Any]:
        """
        Run calculations for every defined scene.
        runner_fn is a callable that takes a Project and returns results.
        Returns {scene_id: results}.
        """
        results: Dict[str, Any] = {}
        base_copy = copy.deepcopy(base_project)
        for sid in self._scenes:
            mgr = SceneManager(base_copy)
            mgr._groups = copy.deepcopy(self._groups)
            mgr._scenes = copy.deepcopy(self._scenes)
            scene_project = mgr.apply_scene_to_project(sid)
            results[sid] = runner_fn(scene_project)
        return results

