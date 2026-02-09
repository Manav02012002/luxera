import pytest

from luxera.engine.ugr_engine import compute_ugr_default
from luxera.geometry.core import Room, Vector3, Material, Transform
from luxera.calculation.illuminance import Luminaire
from luxera.photometry.model import Photometry

pytestmark = pytest.mark.slow


def make_room(width=6.0, length=8.0, height=3.0, refl=(0.2, 0.5, 0.7)):
    return Room.rectangular(
        name="room",
        width=width,
        length=length,
        height=height,
        origin=Vector3(0, 0, 0),
        floor_material=Material(name="floor", reflectance=refl[0]),
        wall_material=Material(name="wall", reflectance=refl[1]),
        ceiling_material=Material(name="ceiling", reflectance=refl[2]),
    )


def make_photometry(intensity=300.0, width=0.6, length=0.6):
    return Photometry(
        system="C",
        c_angles_deg=[0.0],
        gamma_angles_deg=[0.0, 90.0, 180.0],
        candela=[[intensity, intensity * 0.5, 0.0]],
        luminous_flux_lm=1000.0,
        symmetry="FULL",
        tilt=None,
        luminous_width_m=width,
        luminous_length_m=length,
    )


def test_ugr_regression_basic_layout():
    room = make_room()
    phot = make_photometry(intensity=250.0)
    lum = Luminaire(photometry=phot, transform=Transform(position=Vector3(3, 4, 2.8)))

    analysis = compute_ugr_default(room, [lum])
    assert analysis is not None
    assert 10 <= analysis.worst_case_ugr <= 28


def test_ugr_regression_high_luminance_increases_ugr():
    room = make_room()
    low = make_photometry(intensity=150.0)
    high = make_photometry(intensity=600.0)

    lum_low = Luminaire(photometry=low, transform=Transform(position=Vector3(3, 4, 2.8)))
    lum_high = Luminaire(photometry=high, transform=Transform(position=Vector3(3, 4, 2.8)))

    a_low = compute_ugr_default(room, [lum_low])
    a_high = compute_ugr_default(room, [lum_high])
    assert a_low is not None and a_high is not None
    assert a_high.worst_case_ugr >= a_low.worst_case_ugr
