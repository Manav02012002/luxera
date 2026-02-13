from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Union


@dataclass(frozen=True)
class SolidNode:
    kind: Literal["extrusion", "mesh", "primitive"]
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "solid", "kind": self.kind, "params": dict(self.params)}


@dataclass(frozen=True)
class CSGNode:
    op: Literal["union", "diff", "isect"]
    A: "CSGExpr"
    B: "CSGExpr"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "csg",
            "op": self.op,
            "A": _expr_to_dict(self.A),
            "B": _expr_to_dict(self.B),
        }


CSGExpr = Union[SolidNode, CSGNode]


def _expr_to_dict(expr: CSGExpr) -> Dict[str, Any]:
    if isinstance(expr, SolidNode):
        return expr.to_dict()
    return expr.to_dict()


def expr_from_dict(payload: Dict[str, Any]) -> CSGExpr:
    t = str(payload.get("type", ""))
    if t == "solid":
        return SolidNode(
            kind=str(payload["kind"]),  # type: ignore[arg-type]
            params=dict(payload.get("params", {})),
        )
    if t == "csg":
        return CSGNode(
            op=str(payload["op"]),  # type: ignore[arg-type]
            A=expr_from_dict(dict(payload["A"])),
            B=expr_from_dict(dict(payload["B"])),
        )
    raise ValueError("Invalid CSG payload")
