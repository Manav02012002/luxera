from luxera.geometry.core import Room, Vector3, Material
from luxera.calculation.illuminance import Luminaire
from luxera.geometry.core import Transform
from luxera.calculation.radiosity import RadiositySettings
from luxera.engine.radiosity_engine import run_radiosity
from luxera.photometry.model import Photometry


def make_photometry():
    # Simple symmetric distribution
    return Photometry(
        system="C",
        c_angles_deg=[0.0],
        gamma_angles_deg=[0.0, 90.0, 180.0],
        candela=[[100.0, 50.0, 0.0]],
        luminous_flux_lm=None,
        symmetry="FULL",
        tilt=None,
    )


def make_room(reflectance: float) -> Room:
    floor = Material(name="floor", reflectance=reflectance)
    wall = Material(name="wall", reflectance=reflectance)
    ceiling = Material(name="ceiling", reflectance=reflectance)
    return Room.rectangular(
        name="room",
        width=4.0,
        length=4.0,
        height=3.0,
        origin=Vector3(0, 0, 0),
        floor_material=floor,
        wall_material=wall,
        ceiling_material=ceiling,
    )


def test_radiosity_deterministic_seed():
    phot = make_photometry()
    lum = Luminaire(photometry=phot, transform=Transform())
    room = make_room(0.5)

    settings = RadiositySettings(seed=123, use_visibility=False)
    r1 = run_radiosity(room, [lum], settings)
    r2 = run_radiosity(room, [lum], settings)

    assert r1.avg_illuminance == r2.avg_illuminance
    assert r1.residuals == r2.residuals


def test_radiosity_reflectance_monotonic():
    phot = make_photometry()
    lum = Luminaire(photometry=phot, transform=Transform())

    room_low = make_room(0.2)
    room_high = make_room(0.7)

    settings = RadiositySettings(seed=0, use_visibility=False)
    r_low = run_radiosity(room_low, [lum], settings)
    r_high = run_radiosity(room_high, [lum], settings)

    assert r_high.avg_illuminance >= r_low.avg_illuminance
