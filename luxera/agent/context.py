from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RoomContext:
    id: str
    name: str
    dims_m: Dict[str, float]
    materials: Dict[str, Optional[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class LuminaireContext:
    id: str
    name: str
    photometry_asset_id: str
    mounting_height_m: Optional[float]
    tilt_deg: float


@dataclass(frozen=True)
class CalcObjectContext:
    id: str
    kind: str
    metric_set: List[str] = field(default_factory=list)
    pass_fail: Optional[str] = None


@dataclass(frozen=True)
class ConstraintContext:
    target_lux: Optional[float] = None
    uniformity_min: Optional[float] = None
    ugr_max: Optional[float] = None
    max_fittings: Optional[int] = None
    max_spacing_m: Optional[float] = None
    budget: Optional[float] = None


@dataclass(frozen=True)
class ProjectContext:
    project_name: str
    rooms: List[RoomContext] = field(default_factory=list)
    luminaires: List[LuminaireContext] = field(default_factory=list)
    calc_objects: List[CalcObjectContext] = field(default_factory=list)
    constraints: ConstraintContext = field(default_factory=ConstraintContext)
    latest_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentContextMemory:
    """Deterministic per-project agent memory persisted under `.luxera/`."""

    schema_version: int = 1
    turn_count: int = 0
    rolling_summary: Dict[str, Any] = field(
        default_factory=lambda: {
            "geometry": {
                "room_count": 0,
                "surface_count": 0,
                "luminaire_count": 0,
                "grid_count": 0,
            },
            "last_actions": [],
            "last_intent": "",
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(payload: Dict[str, Any]) -> "AgentContextMemory":
        return AgentContextMemory(
            schema_version=int(payload.get("schema_version", 1)),
            turn_count=int(payload.get("turn_count", 0)),
            rolling_summary=dict(payload.get("rolling_summary", {}) or {}),
        )


def context_memory_path(project_path: str | Path) -> Path:
    p = Path(project_path).expanduser().resolve()
    return p.parent / ".luxera" / "agent_context.json"


def load_context_memory(project_path: str | Path) -> AgentContextMemory:
    path = context_memory_path(project_path)
    if not path.exists():
        return AgentContextMemory()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return AgentContextMemory()
    if not isinstance(payload, dict):
        return AgentContextMemory()
    return AgentContextMemory.from_dict(payload)


def save_context_memory(project_path: str | Path, memory: AgentContextMemory) -> AgentContextMemory:
    path = context_memory_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return memory


def reset_context_memory(project_path: str | Path) -> AgentContextMemory:
    return save_context_memory(project_path, AgentContextMemory())


def update_context_memory(
    project_path: str | Path,
    *,
    project: Any,
    intent: str,
    tool_calls: List[Dict[str, Any]],
    run_manifest: Dict[str, Any],
) -> AgentContextMemory:
    alias_map = {
        "add_grid": "project.grid.add",
        "propose_layout_diff": "project.diff.propose_layout",
        "apply_diff": "project.diff.apply",
        "run_job": "job.run",
        "import_geometry": "geom.import",
        "clean_geometry": "geom.clean",
    }
    prev = load_context_memory(project_path)
    rolling = dict(prev.rolling_summary or {})
    geom = dict(rolling.get("geometry", {}) or {})
    geom.update(
        {
            "room_count": int(len(getattr(getattr(project, "geometry", None), "rooms", []) or [])),
            "surface_count": int(len(getattr(getattr(project, "geometry", None), "surfaces", []) or [])),
            "luminaire_count": int(len(getattr(project, "luminaires", []) or [])),
            "grid_count": int(len(getattr(project, "grids", []) or [])),
        }
    )
    rolling["geometry"] = geom
    rolling["last_intent"] = str(intent)
    action_names = []
    for c in tool_calls:
        if not isinstance(c, dict) or not c.get("tool"):
            continue
        raw = str(c.get("tool"))
        action_names.append(alias_map.get(raw, raw))
    previous_actions = list(rolling.get("last_actions", []) or [])
    rolling["last_actions"] = (previous_actions + action_names)[-16:]
    if isinstance(run_manifest, dict) and "runtime_id" in run_manifest:
        rolling["last_runtime_id"] = str(run_manifest.get("runtime_id"))
    updated = AgentContextMemory(
        schema_version=1,
        turn_count=int(prev.turn_count) + 1,
        rolling_summary=rolling,
    )
    return save_context_memory(project_path, updated)
