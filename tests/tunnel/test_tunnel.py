from __future__ import annotations

import pytest

from luxera.tunnel.cie88 import TunnelGeometry, TunnelLightingDesign


def _sample_tunnel() -> TunnelGeometry:
    return TunnelGeometry(
        length_m=800.0,
        width_m=10.5,
        height_m=6.5,
        gradient_pct=2.0,
        orientation_deg=90.0,
        speed_limit_kmh=60.0,
        traffic_volume_veh_h=1200.0,
        portal_type="unshielded",
    )


def test_stopping_distance_60kmh() -> None:
    design = TunnelLightingDesign()
    d = design.stopping_distance(60.0)
    assert d == pytest.approx(42.0, abs=1.0)


def test_l20_unshielded() -> None:
    tunnel = _sample_tunnel()
    design = TunnelLightingDesign()
    l20 = design.compute_L20(tunnel, sky_luminance_cd_m2=5000.0)
    assert 200.0 <= l20 <= 350.0


def test_zones_count() -> None:
    tunnel = _sample_tunnel()
    design = TunnelLightingDesign()
    l20 = design.compute_L20(tunnel, sky_luminance_cd_m2=5000.0)
    zones = design.compute_zones(tunnel, L20=l20)
    assert len(zones) >= 4


def test_threshold_luminance() -> None:
    tunnel = _sample_tunnel()
    design = TunnelLightingDesign()
    l20 = design.compute_L20(tunnel, sky_luminance_cd_m2=5000.0)
    zones = design.compute_zones(tunnel, L20=l20)
    threshold = next(z for z in zones if z.name == "threshold")
    interior = next(z for z in zones if z.name == "interior")
    assert threshold.required_luminance_cd_m2 > interior.required_luminance_cd_m2


def test_transition_decreasing() -> None:
    tunnel = _sample_tunnel()
    design = TunnelLightingDesign()
    l20 = design.compute_L20(tunnel, sky_luminance_cd_m2=5000.0)
    zones = design.compute_zones(tunnel, L20=l20)
    transitions = [z for z in zones if z.name.startswith("transition")]
    assert transitions
    for idx in range(len(transitions) - 1):
        assert (
            transitions[idx].required_luminance_cd_m2
            >= transitions[idx + 1].required_luminance_cd_m2
        )


def test_interior_luminance_range() -> None:
    tunnel = _sample_tunnel()
    design = TunnelLightingDesign()
    l20 = design.compute_L20(tunnel, sky_luminance_cd_m2=5000.0)
    zones = design.compute_zones(tunnel, L20=l20)
    interior = next(z for z in zones if z.name == "interior")
    assert 1.0 <= interior.required_luminance_cd_m2 <= 20.0
