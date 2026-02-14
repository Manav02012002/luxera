from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Set


@dataclass
class ParamGraph:
    kinds: Dict[str, str] = field(default_factory=dict)
    forward: Dict[str, Set[str]] = field(default_factory=dict)
    reverse: Dict[str, Set[str]] = field(default_factory=dict)

    def add_node(self, entity_id: str, kind: str) -> None:
        self.kinds[str(entity_id)] = str(kind)
        self.forward.setdefault(str(entity_id), set())
        self.reverse.setdefault(str(entity_id), set())

    def add_edge(self, depends_on: str, dependent: str) -> None:
        a = str(depends_on)
        b = str(dependent)
        self.forward.setdefault(a, set()).add(b)
        self.reverse.setdefault(b, set()).add(a)
        self.forward.setdefault(b, set())
        self.reverse.setdefault(a, set())

    def affected(self, start_ids: Set[str] | list[str]) -> set[str]:
        q = deque(str(x) for x in start_ids)
        out: set[str] = set()
        while q:
            cur = q.popleft()
            if cur in out:
                continue
            out.add(cur)
            for nxt in sorted(self.forward.get(cur, set())):
                if nxt not in out:
                    q.append(nxt)
        return out


def build_param_graph(project: object) -> ParamGraph:
    """
    Build a dependency DAG between param entities and derived artifacts.
    Node IDs are namespaced with prefixes like "footprint:", "room:", "wall:", "surface:".
    """
    g = ParamGraph()
    param = getattr(project, "param", None)
    if param is None:
        return g

    for fp in getattr(param, "footprints", []):
        g.add_node(f"footprint:{fp.id}", "footprint")
    for room in getattr(param, "rooms", []):
        g.add_node(f"room:{room.id}", "room")
        g.add_node(f"surface:floor:{room.id}", "derived_surface")
        g.add_node(f"surface:ceiling:{room.id}", "derived_surface")
        g.add_edge(f"room:{room.id}", f"surface:floor:{room.id}")
        g.add_edge(f"room:{room.id}", f"surface:ceiling:{room.id}")
        g.add_edge(f"footprint:{room.footprint_id}", f"room:{room.id}")

    for wall in getattr(param, "walls", []):
        g.add_node(f"wall:{wall.id}", "wall")
        g.add_node(f"surface:wall:{wall.id}", "derived_surface")
        g.add_edge(f"room:{wall.room_id}", f"wall:{wall.id}")
        g.add_edge(f"wall:{wall.id}", f"surface:wall:{wall.id}")

    for sw in getattr(param, "shared_walls", []):
        g.add_node(f"shared_wall:{sw.id}", "shared_wall")
        g.add_node(f"surface:shared_wall:{sw.id}", "derived_surface")
        g.add_edge(f"room:{sw.room_a}", f"shared_wall:{sw.id}")
        if sw.room_b is not None:
            g.add_edge(f"room:{sw.room_b}", f"shared_wall:{sw.id}")
        g.add_edge(f"shared_wall:{sw.id}", f"surface:shared_wall:{sw.id}")

    for op in getattr(param, "openings", []):
        g.add_node(f"opening:{op.id}", "opening")
        g.add_edge(f"wall:{op.wall_id}", f"opening:{op.id}")
        g.add_edge(f"opening:{op.id}", f"surface:wall:{op.wall_id}")

    for zone in getattr(param, "zones", []):
        g.add_node(f"zone:{zone.id}", "zone")
        g.add_edge(f"room:{zone.room_id}", f"zone:{zone.id}")

    for grid in getattr(project, "grids", []):
        gid = getattr(grid, "id", "")
        room_id = getattr(grid, "room_id", None)
        zone_id = getattr(grid, "zone_id", None)
        if not gid:
            continue
        g.add_node(f"grid:{gid}", "derived_grid")
        if room_id:
            g.add_edge(f"room:{room_id}", f"grid:{gid}")
        if zone_id:
            g.add_edge(f"zone:{zone_id}", f"grid:{gid}")

    return g
