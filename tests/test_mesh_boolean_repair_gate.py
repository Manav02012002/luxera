from __future__ import annotations

import pytest

from luxera.geometry.csg.mesh_ops import mesh_boolean_with_repair_gate
from luxera.geometry.csg.ops import extrusion_node
from luxera.geometry.csg.tree import CSGNode


def test_mesh_boolean_repair_gate_outputs_valid_mesh() -> None:
    room = extrusion_node([(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)], z0=0.0, height=3.0)
    shaft = extrusion_node([(2.0, 1.0), (4.0, 1.0), (4.0, 3.0), (2.0, 3.0)], z0=0.0, height=3.0)
    tree = CSGNode(op="diff", A=room, B=shaft)
    out = mesh_boolean_with_repair_gate(tree)
    if not out.ok and "backend unavailable" in out.message.lower():
        pytest.skip("2D boolean backend unavailable")
    assert out.ok
    assert out.mesh is not None
    out.mesh.validate()
