from __future__ import annotations

from luxera.calcs.objects import HorizontalGrid, LineGrid, calc_object_from_dict, serialize_calc_objects


def test_calc_objects_roundtrip_serialization() -> None:
    objs = [
        HorizontalGrid(id="h1", name="wp", width=4.0, height=3.0, rows=5, cols=4),
        LineGrid(id="l1", name="route", polyline=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], spacing=0.25),
    ]
    rows = serialize_calc_objects(objs)
    assert len(rows) == 2
    back0 = calc_object_from_dict(rows[0])
    back1 = calc_object_from_dict(rows[1])
    assert back0.object_type == "HorizontalGrid"
    assert back1.object_type == "LineGrid"

