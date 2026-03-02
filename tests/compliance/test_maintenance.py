from __future__ import annotations

from luxera.compliance.maintenance import MAINTENANCE_PROFILES, compute_maintenance_factors


def test_led_clean_mf_high():
    comp = compute_maintenance_factors(MAINTENANCE_PROFILES["led_office_clean"])
    assert comp.mf > 0.85


def test_metal_halide_dirty_mf_low():
    comp = compute_maintenance_factors(MAINTENANCE_PROFILES["metal_halide_warehouse"])
    assert comp.mf < 0.60


def test_mf_product_equals_components():
    comp = compute_maintenance_factors(MAINTENANCE_PROFILES["t5_office"])
    product = comp.llmf * comp.lsf * comp.lmf * comp.rsf
    assert abs(comp.mf - product) < 1e-12


def test_all_profiles_valid():
    for profile in MAINTENANCE_PROFILES.values():
        comp = compute_maintenance_factors(profile)
        assert 0.3 <= comp.mf <= 1.0


def test_components_between_0_and_1():
    for profile in MAINTENANCE_PROFILES.values():
        comp = compute_maintenance_factors(profile)
        assert 0.0 <= comp.llmf <= 1.0
        assert 0.0 <= comp.lsf <= 1.0
        assert 0.0 <= comp.lmf <= 1.0
        assert 0.0 <= comp.rsf <= 1.0

