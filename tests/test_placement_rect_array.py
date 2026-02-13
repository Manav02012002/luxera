from __future__ import annotations

from luxera.design.placement import place_along_polyline, place_array_rect, place_rect_array


def test_place_array_rect_count_spacing_bounds() -> None:
    room_bounds = (0.0, 0.0, 10.0, 8.0)
    arr = place_array_rect(
        room_bounds=room_bounds,
        nx=4,
        ny=3,
        margin_x=1.0,
        margin_y=1.0,
        z=2.8,
        photometry_asset_id="asset1",
        rotation=(0.0, 0.0, 0.0),
    )
    assert len(arr) == 12
    xs = sorted({round(l.transform.position[0], 6) for l in arr})
    ys = sorted({round(l.transform.position[1], 6) for l in arr})
    assert xs[0] >= 1.0 and xs[-1] <= 9.0
    assert ys[0] >= 1.0 and ys[-1] <= 7.0
    dx = [round(xs[i + 1] - xs[i], 6) for i in range(len(xs) - 1)]
    dy = [round(ys[i + 1] - ys[i], 6) for i in range(len(ys) - 1)]
    assert max(dx) - min(dx) < 1e-5
    assert max(dy) - min(dy) < 1e-5


def test_place_rect_array_api_count_bounds() -> None:
    arr = place_rect_array(
        room_bounds=(0.0, 0.0, 10.0, 8.0),
        nx=3,
        ny=2,
        margins=(1.0, 0.5),
        mount_height=2.8,
        photometry_asset_id="asset1",
    )
    assert len(arr) == 6
    for lum in arr:
        x, y, z = lum.transform.position
        assert 1.0 <= x <= 9.0
        assert 0.5 <= y <= 7.5
        assert z == 2.8


def test_place_along_polyline_spacing() -> None:
    out = place_along_polyline(
        polyline=[(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)],
        spacing=2.0,
        start_offset=1.0,
        mount_height=6.0,
        photometry_asset_id="asset1",
    )
    xs = [round(l.transform.position[0], 6) for l in out]
    assert xs == [1.0, 3.0, 5.0, 7.0, 9.0]
