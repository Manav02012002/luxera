from __future__ import annotations

import builtins
from pathlib import Path

from luxera.io.mesh_import import import_mesh_file


def test_import_obj_edge_whitespace_and_negative_indices() -> None:
    path = Path("tests/fixtures/mesh/edge_whitespace_negative.obj").resolve()
    out = import_mesh_file(str(path), fmt="OBJ")
    assert out.format == "OBJ"
    assert len(out.vertices) >= 5
    assert len(out.faces) == 2
    assert len(out.triangles) == 3  # quad -> 2 + tri -> 1


def test_import_gltf_fallback_extras_without_trimesh(monkeypatch) -> None:
    path = Path("tests/fixtures/mesh/fallback_extras.gltf").resolve()

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "trimesh":
            raise ImportError("blocked for fallback test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    out = import_mesh_file(str(path), fmt="GLTF")
    assert out.format == "GLTF"
    assert len(out.vertices) == 4
    assert len(out.faces) == 2
    assert len(out.triangles) == 2
    assert any("fallback" in w.lower() for w in out.warnings)
