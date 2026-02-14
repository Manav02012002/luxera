from __future__ import annotations

from typing import Iterable, Optional

from luxera.project.schema import LayerSpec, Project


def layer_table(project: Project) -> dict[str, LayerSpec]:
    return {str(l.id): l for l in project.layers}


def object_layer_id(obj: object, default: Optional[str] = None) -> Optional[str]:
    lid = getattr(obj, "layer_id", None)
    if lid is not None:
        return str(lid)
    legacy = getattr(obj, "layer", None)
    if legacy is not None:
        return str(legacy)
    return default


def layer_visible(project: Project, layer_id: Optional[str]) -> bool:
    if layer_id is None:
        return True
    l = layer_table(project).get(str(layer_id))
    if l is None:
        return True
    return bool(l.visible)


def filter_visible(project: Project, objects: Iterable[object], *, default_layer: Optional[str] = None) -> list[object]:
    out: list[object] = []
    for obj in objects:
        lid = object_layer_id(obj, default=default_layer)
        if layer_visible(project, lid):
            out.append(obj)
    return out

