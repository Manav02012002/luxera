from __future__ import annotations

from luxera.gui.scene_node_binding import resolve_scene_node_update
from luxera.project.schema import (
    CalcGrid,
    LuminaireInstance,
    Project,
    RotationSpec,
    RoomSpec,
    SurfaceSpec,
    TransformSpec,
)


def _project() -> Project:
    p = Project(name="bind")
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=4.0, length=5.0, height=3.0, origin=(0.0, 0.0, 0.0)))
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="s1",
            name="S",
            kind="wall",
            vertices=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 0.0, 1.0), (0.0, 0.0, 1.0)],
            room_id="r1",
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(1.0, 1.0, 2.0), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G", origin=(0.0, 0.0, 0.0), width=2.0, height=2.0, elevation=0.8, nx=3, ny=3))
    return p


def test_scene_node_binding_for_room() -> None:
    p = _project()
    kind, oid, payload = resolve_scene_node_update(p, "room:r1", {"tx": 2.0, "ty": 3.0, "tz": 0.5, "name": "Room X"})
    assert kind == "room"
    assert oid == "r1"
    assert payload["origin"] == (2.0, 3.0, 0.5)
    assert payload["name"] == "Room X"


def test_scene_node_binding_for_luminaire_transform() -> None:
    p = _project()
    kind, oid, payload = resolve_scene_node_update(
        p,
        "luminaire:l1",
        {"tx": 2.5, "ty": 2.0, "tz": 2.8, "yaw_deg": 10.0, "pitch_deg": 5.0, "roll_deg": -3.0},
    )
    assert kind == "luminaire"
    assert oid == "l1"
    tf = payload["transform"]
    assert isinstance(tf, TransformSpec)
    assert tf.position == (2.5, 2.0, 2.8)
    assert tf.rotation.euler_deg == (10.0, 5.0, -3.0)


def test_scene_node_binding_for_surface_material_and_translation() -> None:
    p = _project()
    kind, oid, payload = resolve_scene_node_update(p, "surface:s1", {"tx": 2.0, "ty": 2.0, "tz": 0.0, "material_id": "mat1"})
    assert kind == "surface"
    assert oid == "s1"
    assert payload["material_id"] == "mat1"
    verts = payload["vertices"]
    assert verts[0] == (2.0, 2.0, 0.0)
