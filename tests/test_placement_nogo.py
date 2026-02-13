from __future__ import annotations

from luxera.design.placement import place_rect_array


def test_place_rect_array_respects_no_go_polygon() -> None:
    blocked = [(4.0, 2.0), (6.0, 2.0), (6.0, 4.0), (4.0, 4.0)]
    arr = place_rect_array(
        room_bounds=(0.0, 0.0, 10.0, 8.0),
        nx=5,
        ny=4,
        margins=1.0,
        mount_height=2.8,
        photometry_asset_id="asset1",
        no_go_polygons=[blocked],
    )
    assert arr
    for lum in arr:
        x, y, _ = lum.transform.position
        assert not (4.0 < x < 6.0 and 2.0 < y < 4.0)
