from luxera.engine.ugr_engine import compute_ugr_for_views
from luxera.geometry.core import Room, Vector3, Material, Transform
from luxera.calculation.illuminance import Luminaire
from luxera.photometry.model import Photometry
from luxera.project.schema import GlareViewSpec


def _make_scene(offset=(0.0, 0.0, 0.0)):
    ox, oy, oz = offset
    room = Room.rectangular(
        name="room",
        width=4.0,
        length=4.0,
        height=3.0,
        origin=Vector3(ox, oy, oz),
        floor_material=Material(name="floor", reflectance=0.2),
        wall_material=Material(name="wall", reflectance=0.5),
        ceiling_material=Material(name="ceiling", reflectance=0.7),
    )
    phot = Photometry(
        system="C",
        c_angles_deg=[0.0],
        gamma_angles_deg=[0.0, 90.0, 180.0],
        candela=[[200.0, 100.0, 0.0]],
        luminous_flux_lm=1000.0,
        symmetry="FULL",
        tilt=None,
        luminous_width_m=0.6,
        luminous_length_m=0.6,
    )
    lum = Luminaire(photometry=phot, transform=Transform(position=Vector3(2.0 + ox, 2.0 + oy, 2.8 + oz)))
    view = GlareViewSpec(
        id="v1",
        name="view",
        observer=(1.0 + ox, 1.0 + oy, 1.2 + oz),
        view_dir=(1.0, 0.0, 0.0),
    )
    return room, [lum], [view]


def test_ugr_for_views_translation_invariance():
    room1, lums1, views1 = _make_scene((0.0, 0.0, 0.0))
    room2, lums2, views2 = _make_scene((10.0, -5.0, 0.0))

    a1 = compute_ugr_for_views(room1, lums1, views1)
    a2 = compute_ugr_for_views(room2, lums2, views2)
    assert a1 is not None and a2 is not None
    assert abs(a1.worst_case_ugr - a2.worst_case_ugr) < 1e-6
