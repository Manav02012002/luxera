from __future__ import annotations

from typing import Any, Dict, List, Tuple

from luxera.ops.delta import Delta, DeltaItem


def _pairs(before: Dict[str, Any], after: Dict[str, Any], path: Tuple[str, ...]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    b = before
    a = after
    for key in path:
        b = b.get(key, {})
        a = a.get(key, {})
    return list(b if isinstance(b, list) else []), list(a if isinstance(a, list) else [])


def _index(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for raw in items:
        if isinstance(raw, dict) and "id" in raw:
            out[str(raw["id"])] = raw
    return out


def diff_collections(
    before: Dict[str, Any],
    after: Dict[str, Any],
    *,
    kind: str,
    path: Tuple[str, ...],
) -> Delta:
    b_items, a_items = _pairs(before, after, path)
    b_idx = _index(b_items)
    a_idx = _index(a_items)
    created: List[DeltaItem] = []
    updated: List[DeltaItem] = []
    deleted: List[DeltaItem] = []

    for item_id in sorted(set(a_idx) - set(b_idx)):
        created.append(DeltaItem(kind=kind, id=item_id, before=None, after=dict(a_idx[item_id])))
    for item_id in sorted(set(b_idx) - set(a_idx)):
        deleted.append(DeltaItem(kind=kind, id=item_id, before=dict(b_idx[item_id]), after=None))
    for item_id in sorted(set(a_idx) & set(b_idx)):
        if a_idx[item_id] != b_idx[item_id]:
            updated.append(
                DeltaItem(
                    kind=kind,
                    id=item_id,
                    before=dict(b_idx[item_id]),
                    after=dict(a_idx[item_id]),
                )
            )
    return Delta(created=created, updated=updated, deleted=deleted)


def combine_deltas(deltas: List[Delta]) -> Delta:
    created: List[DeltaItem] = []
    updated: List[DeltaItem] = []
    deleted: List[DeltaItem] = []
    for d in deltas:
        created.extend(d.created)
        updated.extend(d.updated)
        deleted.extend(d.deleted)
    return Delta(created=created, updated=updated, deleted=deleted)


def diff_project(before: Dict[str, Any], after: Dict[str, Any]) -> Delta:
    deltas = [
        diff_collections(before, after, kind="room", path=("geometry", "rooms")),
        diff_collections(before, after, kind="surface", path=("geometry", "surfaces")),
        diff_collections(before, after, kind="opening", path=("geometry", "openings")),
        diff_collections(before, after, kind="material", path=("materials",)),
        diff_collections(before, after, kind="grid", path=("grids",)),
        diff_collections(before, after, kind="workplane", path=("workplanes",)),
        diff_collections(before, after, kind="vertical_plane", path=("vertical_planes",)),
        diff_collections(before, after, kind="point_set", path=("point_sets",)),
    ]
    return combine_deltas(deltas)

