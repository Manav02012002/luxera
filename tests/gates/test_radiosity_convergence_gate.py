from __future__ import annotations

from luxera.calculation.radiosity import RadiositySettings
from luxera.calculation.illuminance import Luminaire
from luxera.engine.radiosity_engine import run_radiosity
from luxera.geometry.core import Material, Room, Transform, Vector3
from luxera.photometry.model import Photometry


def _photometry() -> Photometry:
    return Photometry(
        system="C",
        c_angles_deg=[0.0],
        gamma_angles_deg=[0.0, 45.0, 90.0, 180.0],
        candela=[[250.0, 180.0, 80.0, 0.0]],
        luminous_flux_lm=None,
        symmetry="FULL",
        tilt=None,
    )


def _room() -> Room:
    return Room.rectangular(
        name="gate_room",
        width=5.0,
        length=5.0,
        height=3.0,
        origin=Vector3(0.0, 0.0, 0.0),
        floor_material=Material(name="floor", reflectance=0.2),
        wall_material=Material(name="wall", reflectance=0.5),
        ceiling_material=Material(name="ceiling", reflectance=0.7),
    )


def test_radiosity_gate_deterministic_and_stable_residual() -> None:
    room = _room()
    lum = Luminaire(photometry=_photometry(), transform=Transform(position=Vector3(2.5, 2.5, 2.8)))
    settings = RadiositySettings(
        seed=42,
        use_visibility=False,
        patch_max_area=4.0,
        max_iterations=40,
        convergence_threshold=5e-4,
    )

    a = run_radiosity(room, [lum], settings)
    b = run_radiosity(room, [lum], settings)

    assert a.residuals == b.residuals
    assert a.energy_balance_history == b.energy_balance_history
    assert a.iterations == b.iterations

    assert a.residuals, "expected residual history"
    assert a.residuals[-1] <= a.residuals[0] + 1e-12
    assert all(a.residuals[i + 1] <= a.residuals[i] + 1e-12 for i in range(len(a.residuals) - 1))
