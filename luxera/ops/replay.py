from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from luxera.project.schema import Project
from luxera.scene.build import build_scene_graph_from_project
from luxera.scene.scene_graph import SceneGraph, SceneNode


@dataclass(frozen=True)
class ReplayResult:
    scene_graph: SceneGraph
    applied_events: int
    skipped_events: int
    hash_chain_ok: bool


def replay_agent_history_to_scene_graph(project: Project, *, strict_hash_chain: bool = False) -> ReplayResult:
    graph = build_scene_graph_from_project(project)
    applied = 0
    skipped = 0
    hash_ok = True
    events = list(project.agent_history)
    prev_after = None
    for event in events:
        if not isinstance(event, dict):
            skipped += 1
            continue
        action = str(event.get("action", ""))
        if not action.startswith("ops."):
            skipped += 1
            continue
        if strict_hash_chain:
            before = event.get("before_hash")
            if prev_after is not None and before is not None and before != prev_after:
                hash_ok = False
            prev_after = event.get("after_hash")
        if _apply_event(graph, action, event.get("args", {})):
            applied += 1
        else:
            skipped += 1
    return ReplayResult(scene_graph=graph, applied_events=applied, skipped_events=skipped, hash_chain_ok=hash_ok)


def _apply_event(graph: SceneGraph, action: str, args: Any) -> bool:
    a = dict(args) if isinstance(args, dict) else {}
    try:
        if action == "ops.create_room":
            rid = str(a.get("room_id"))
            if rid and not _has(graph, f"room:{rid}"):
                graph.add_node(SceneNode(id=f"room:{rid}", name=str(a.get("name", rid)), type="room", parent="group:rooms" if _has(graph, "group:rooms") else None))
            return True
        if action == "ops.create_wall_polygon":
            sid = str(a.get("surface_id"))
            room_id = a.get("room_id")
            parent = f"room:{room_id}" if room_id and _has(graph, f"room:{room_id}") else None
            if sid and not _has(graph, f"surface:{sid}"):
                graph.add_node(SceneNode(id=f"surface:{sid}", name=str(a.get("name", sid)), type="wall", parent=parent, mesh_ref=sid))
            return True
        if action == "ops.add_opening":
            oid = str(a.get("opening_id"))
            hs = a.get("host_surface_id")
            parent = f"surface:{hs}" if hs and _has(graph, f"surface:{hs}") else None
            if oid and not _has(graph, f"opening:{oid}"):
                graph.add_node(SceneNode(id=f"opening:{oid}", name=str(a.get("name", oid)), type=str(a.get("opening_type", "opening")), parent=parent, mesh_ref=oid))
            return True
        if action == "ops.create_calc_grid_from_room":
            gid = str(a.get("grid_id"))
            room_id = str(a.get("room_id", ""))
            parent = f"room:{room_id}" if room_id and _has(graph, f"room:{room_id}") else "group:calcs" if _has(graph, "group:calcs") else None
            if gid and not _has(graph, f"grid:{gid}"):
                graph.add_node(SceneNode(id=f"grid:{gid}", name=str(a.get("name", gid)), type="grid", parent=parent))
            return True
        return False
    except Exception:
        return False


def _has(graph: SceneGraph, node_id: str) -> bool:
    try:
        _ = graph.get_node(node_id)
        return True
    except KeyError:
        return False
