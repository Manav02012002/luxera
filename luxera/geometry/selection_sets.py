from __future__ import annotations

from typing import Iterable, List, Set

from luxera.project.schema import Project, SelectionSetSpec


def _surface_ids(project: Project, predicate) -> List[str]:
    return [s.id for s in project.geometry.surfaces if predicate(s)]


def query_all_walls_in_room(project: Project, room_id: str) -> List[str]:
    return _surface_ids(project, lambda s: s.kind == "wall" and s.room_id == room_id)


def query_all_ceilings_in_storey(project: Project, level_id: str) -> List[str]:
    room_ids = {r.id for r in project.geometry.rooms if str(r.level_id or "") == str(level_id)}
    return _surface_ids(project, lambda s: s.kind == "ceiling" and s.room_id in room_ids)


def query_by_material(project: Project, material_id: str) -> List[str]:
    return _surface_ids(project, lambda s: str(s.material_id or "") == str(material_id))


def query_by_tag(project: Project, tag: str) -> List[str]:
    t = str(tag)
    return _surface_ids(project, lambda s: t in set(str(x) for x in (s.tags or [])))


def query_by_layer(project: Project, layer_id: str) -> List[str]:
    lid = str(layer_id)
    out: List[str] = []
    for s in project.geometry.surfaces:
        sid = s.layer_id if s.layer_id is not None else s.layer
        if str(sid or "") == lid:
            out.append(s.id)
    return out


def _evaluate_query(project: Project, query: str) -> List[str]:
    q = str(query).strip()
    if not q:
        return []
    if q.startswith("walls_in_room:"):
        return query_all_walls_in_room(project, q.split(":", 1)[1])
    if q.startswith("ceilings_in_storey:"):
        return query_all_ceilings_in_storey(project, q.split(":", 1)[1])
    if q.startswith("material:"):
        return query_by_material(project, q.split(":", 1)[1])
    if q.startswith("tag:"):
        return query_by_tag(project, q.split(":", 1)[1])
    if q.startswith("layer:"):
        return query_by_layer(project, q.split(":", 1)[1])
    return []


def refresh_selection_sets(project: Project) -> None:
    for s in project.selection_sets:
        if s.query:
            s.object_ids = sorted(set(_evaluate_query(project, s.query)))


def selection_set(project: Project, set_id: str) -> SelectionSetSpec | None:
    return next((s for s in project.selection_sets if s.id == set_id), None)


def upsert_selection_set(project: Project, spec: SelectionSetSpec) -> SelectionSetSpec:
    cur = selection_set(project, spec.id)
    if cur is None:
        project.selection_sets.append(spec)
        cur = spec
    else:
        cur.name = spec.name
        cur.query = spec.query
        cur.tags = list(spec.tags)
        cur.object_ids = list(spec.object_ids)
    if cur.query:
        cur.object_ids = sorted(set(_evaluate_query(project, cur.query)))
    return cur


def remap_selection_sets(project: Project, stable_id_map: dict[str, List[str]], attachment_remap: dict[str, str]) -> None:
    reverse_parent: dict[str, Set[str]] = {}
    for child, parent in attachment_remap.items():
        reverse_parent.setdefault(parent, set()).add(child)
    for ss in project.selection_sets:
        remapped: Set[str] = set()
        for oid in ss.object_ids:
            if oid in stable_id_map and stable_id_map[oid]:
                remapped.update(stable_id_map[oid])
                continue
            children = reverse_parent.get(oid)
            if children:
                remapped.update(children)
            else:
                remapped.add(oid)
        ss.object_ids = sorted(remapped)
    refresh_selection_sets(project)

