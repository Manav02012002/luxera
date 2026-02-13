from __future__ import annotations

import pytest

from luxera.geometry.csg.ops import eval_csg, extrusion_node
from luxera.geometry.csg.tree import CSGNode


def test_csg_extrusion_diff_shaft_subtraction_from_room() -> None:
    room = extrusion_node([(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)], z0=0.0, height=3.0)
    shaft = extrusion_node([(2.0, 1.0), (4.0, 1.0), (4.0, 3.0), (2.0, 3.0)], z0=0.0, height=3.0)
    tree = CSGNode(op="diff", A=room, B=shaft)
    out = eval_csg(tree)
    if not out.ok and out.error is not None and out.error.code == "backend_unavailable":
        pytest.skip("2D boolean backend unavailable")
    assert out.ok
    assert out.solids
    assert all(s.kind == "extrusion" for s in out.solids)
