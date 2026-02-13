from __future__ import annotations

from pathlib import Path

from luxera.ifc.importer import import_ifc_deterministic
from luxera.io.ifc_import import IFCImportOptions


def test_ifc_import_builds_semantic_scene_graph() -> None:
    fixture = Path("tests/fixtures/ifc/simple_office.ifc").resolve()
    out = import_ifc_deterministic(fixture, IFCImportOptions())
    assert out.scene_graph.nodes
    assert out.scene_graph.rooms
    room_nodes = [n for n in out.scene_graph.nodes if n.type == "room"]
    assert room_nodes
    assert any(n.parent is not None for n in room_nodes)
    assert set(out.semantic_groups.keys()) >= {"levels", "spaces", "surfaces", "openings"}
