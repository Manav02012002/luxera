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
    specs = [
        ("room", ("geometry", "rooms")),
        ("surface", ("geometry", "surfaces")),
        ("opening", ("geometry", "openings")),
        ("obstruction", ("geometry", "obstructions")),
        ("level", ("geometry", "levels")),
        ("material", ("materials",)),
        ("grid", ("grids",)),
        ("workplane", ("workplanes",)),
        ("vertical_plane", ("vertical_planes",)),
        ("arbitrary_plane", ("arbitrary_planes",)),
        ("point_set", ("point_sets",)),
        ("line_grid", ("line_grids",)),
        ("glare_view", ("glare_views",)),
        ("escape_route", ("escape_routes",)),
        ("roadway", ("roadways",)),
        ("roadway_grid", ("roadway_grids",)),
        ("luminaire", ("luminaires",)),
        ("asset", ("photometry_assets",)),
        ("family", ("luminaire_families",)),
        ("variant", ("variants",)),
        ("layer", ("layers",)),
        ("symbol_2d", ("symbols_2d",)),
        ("block_instance", ("block_instances",)),
        ("selection_set", ("selection_sets",)),
        ("param_footprint", ("param", "footprints")),
        ("param_room", ("param", "rooms")),
        ("param_wall", ("param", "walls")),
        ("param_shared_wall", ("param", "shared_walls")),
        ("param_opening", ("param", "openings")),
        ("param_slab", ("param", "slabs")),
        ("param_zone", ("param", "zones")),
        ("param_instance", ("param", "instances")),
    ]
    deltas = [diff_collections(before, after, kind=k, path=p) for k, p in specs]
    out = combine_deltas(deltas)
    param_changes = {
        "created": [i.id for i in out.created if i.kind.startswith("param_")],
        "updated": [i.id for i in out.updated if i.kind.startswith("param_")],
        "deleted": [i.id for i in out.deleted if i.kind.startswith("param_")],
    }
    return Delta(
        created=list(out.created),
        updated=list(out.updated),
        deleted=list(out.deleted),
        param_changes=param_changes,
        derived_regen_summary=dict(out.derived_regen_summary),
        stable_id_map=dict(out.stable_id_map),
        attachment_remap=dict(out.attachment_remap),
    )
