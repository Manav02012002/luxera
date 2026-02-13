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

