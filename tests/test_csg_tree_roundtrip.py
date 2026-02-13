from __future__ import annotations

from luxera.geometry.csg.tree import CSGNode, SolidNode, expr_from_dict


def test_csg_tree_roundtrip() -> None:
    room = SolidNode(kind="extrusion", params={"profile": [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)], "z0": 0.0, "z1": 3.0})
    shaft = SolidNode(kind="extrusion", params={"profile": [(2.0, 1.0), (4.0, 1.0), (4.0, 3.0), (2.0, 3.0)], "z0": 0.0, "z1": 3.0})
    tree = CSGNode(op="diff", A=room, B=shaft)

    data = tree.to_dict()
    rebuilt = expr_from_dict(data)
    assert rebuilt.to_dict() == data  # type: ignore[union-attr]
