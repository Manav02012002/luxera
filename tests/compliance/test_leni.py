from __future__ import annotations

from luxera.compliance.energy import LENIInputs, LENI_PROFILES, compute_leni


def test_leni_simple_office():
    base = LENI_PROFILES["office_open_plan"]
    result = compute_leni(
        LENIInputs(
            installed_power_W=1200.0,
            room_area_m2=100.0,
            annual_operating_hours=base.annual_operating_hours,
            daylight_dependent_hours=base.daylight_dependent_hours,
            non_occupied_hours=base.non_occupied_hours,
            occupancy_factor=base.occupancy_factor,
            daylight_factor_constant=base.daylight_factor_constant,
            daylight_factor_supply=base.daylight_factor_supply,
            absence_factor=base.absence_factor,
            parasitic_power_W=0.0,
            emergency_power_W=0.0,
            emergency_hours=0.0,
        )
    )
    assert 10.0 <= result.leni_kWh_per_m2_year <= 40.0


def test_leni_zero_power():
    result = compute_leni(
        LENIInputs(
            installed_power_W=0.0,
            room_area_m2=100.0,
            annual_operating_hours=2500.0,
            daylight_dependent_hours=1800.0,
            non_occupied_hours=6260.0,
            occupancy_factor=0.9,
            daylight_factor_constant=0.9,
            daylight_factor_supply=0.6,
            absence_factor=0.1,
            parasitic_power_W=10.0,
            emergency_power_W=0.0,
            emergency_hours=0.0,
        )
    )
    expected = (10.0 * (8760.0 - 2500.0) / 1000.0) / 100.0
    assert abs(result.leni_kWh_per_m2_year - expected) < 1e-9


def test_leni_no_daylight():
    base = LENIInputs(
        installed_power_W=1200.0,
        room_area_m2=100.0,
        annual_operating_hours=2500.0,
        daylight_dependent_hours=1800.0,
        non_occupied_hours=6260.0,
        occupancy_factor=0.9,
        daylight_factor_constant=0.9,
        daylight_factor_supply=0.0,
        absence_factor=0.1,
        parasitic_power_W=0.0,
        emergency_power_W=0.0,
        emergency_hours=0.0,
    )
    res_no_daylight = compute_leni(base)
    res_with_daylight = compute_leni(
        LENIInputs(
            **{
                **base.__dict__,
                "daylight_factor_supply": 0.8,
            }
        )
    )
    assert res_no_daylight.leni_kWh_per_m2_year > res_with_daylight.leni_kWh_per_m2_year


def test_leni_full_daylight():
    low = compute_leni(
        LENIInputs(
            installed_power_W=1200.0,
            room_area_m2=100.0,
            annual_operating_hours=2500.0,
            daylight_dependent_hours=2500.0,
            non_occupied_hours=6260.0,
            occupancy_factor=0.9,
            daylight_factor_constant=0.95,
            daylight_factor_supply=0.9,
            absence_factor=0.1,
            parasitic_power_W=0.0,
            emergency_power_W=0.0,
            emergency_hours=0.0,
        )
    )
    high = compute_leni(
        LENIInputs(
            installed_power_W=1200.0,
            room_area_m2=100.0,
            annual_operating_hours=2500.0,
            daylight_dependent_hours=0.0,
            non_occupied_hours=6260.0,
            occupancy_factor=0.9,
            daylight_factor_constant=0.95,
            daylight_factor_supply=0.0,
            absence_factor=0.1,
            parasitic_power_W=0.0,
            emergency_power_W=0.0,
            emergency_hours=0.0,
        )
    )
    assert low.leni_kWh_per_m2_year < high.leni_kWh_per_m2_year


def test_all_profiles_exist():
    assert len(LENI_PROFILES) >= 9


def test_power_density():
    result = compute_leni(
        LENIInputs(
            installed_power_W=1200.0,
            room_area_m2=100.0,
            annual_operating_hours=2500.0,
            daylight_dependent_hours=1800.0,
            non_occupied_hours=6260.0,
            occupancy_factor=0.9,
            daylight_factor_constant=0.9,
            daylight_factor_supply=0.6,
            absence_factor=0.1,
            parasitic_power_W=0.0,
            emergency_power_W=0.0,
            emergency_hours=0.0,
        )
    )
    assert abs(result.power_density_W_per_m2 - 12.0) < 1e-9
    assert abs(result.normalised_power_pn - 12.0) < 1e-9

