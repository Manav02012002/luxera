from luxera.engine.ugr_engine import compute_ugr_default
from luxera.geometry.core import Room, Vector3, Material, Transform
from luxera.calculation.illuminance import Luminaire
from luxera.photometry.model import Photometry


def test_ugr_default_returns_analysis():
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

    lum = Luminaire(photometry=phot, transform=Transform(position=Vector3(2, 2, 2.8)))
    room = Room.rectangular(
        name="room",
        width=4.0,
        length=4.0,
        height=3.0,
        origin=Vector3(0, 0, 0),
        floor_material=Material(name="floor", reflectance=0.2),
        wall_material=Material(name="wall", reflectance=0.5),
        ceiling_material=Material(name="ceiling", reflectance=0.7),
    )

    analysis = compute_ugr_default(room, [lum])
    assert analysis is not None
    assert analysis.worst_case_ugr >= 0
