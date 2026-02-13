from __future__ import annotations

from pathlib import Path

from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import Project


def test_project_layers_persist_visibility(tmp_path: Path) -> None:
    project = Project(name="layers")
    layer = next(l for l in project.layers if l.id == "luminaire")
    layer.visible = False
    p = tmp_path / "p.json"
    save_project_schema(project, p)
    loaded = load_project_schema(p)
    loaded_layer = next(l for l in loaded.layers if l.id == "luminaire")
    assert loaded_layer.visible is False

