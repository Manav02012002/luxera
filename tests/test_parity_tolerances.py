from __future__ import annotations

from pathlib import Path

from luxera.parity.tolerances import (
    array_thresholds,
    load_tolerance_file,
    resolve_profile,
    scalar_tolerance,
)


def test_profile_resolution_with_tags() -> None:
    profiles = {
        "default": {
            "scalar": {"abs": 0.01, "rel": 0.01, "near_zero_abs": 0.1},
            "arrays": {"default": {"max_abs": 0.2, "rmse_abs": 0.1, "p95_abs": 0.15, "p99_abs": 0.2}},
        },
        "profiles": [
            {"when_tags": ["fast"], "scalar": {"abs": 0.02}},
            {"when_tags_all": ["nightly", "strict"], "scalar": {"rel": 0.001}},
        ],
    }

    p_fast = resolve_profile("indoor_illuminance", profiles, {"fast"})
    assert p_fast["scalar"]["abs"] == 0.02
    assert p_fast["scalar"]["rel"] == 0.01

    p_strict = resolve_profile("indoor_illuminance", profiles, {"nightly", "strict"})
    assert p_strict["scalar"]["abs"] == 0.01
    assert p_strict["scalar"]["rel"] == 0.001


def test_scalar_tolerance_lookup() -> None:
    profile = {
        "scalar": {
            "abs": 0.01,
            "rel": 0.01,
            "near_zero_abs": 0.1,
            "metrics": {
                "mean_lux": {"abs": 0.02, "rel": 0.002},
                "roadway": {"abs": 0.5, "rel": 0.0, "near_zero_abs": 0.5},
            },
        }
    }

    t_mean = scalar_tolerance(profile, "mean_lux")
    assert t_mean["abs"] == 0.02
    assert t_mean["rel"] == 0.002
    assert t_mean["near_zero_abs"] == 0.1

    t_prefix = scalar_tolerance(profile, "roadway.lane_1")
    assert t_prefix["abs"] == 0.5
    assert t_prefix["rel"] == 0.0
    assert t_prefix["near_zero_abs"] == 0.5


def test_array_thresholds_lookup() -> None:
    profile = {
        "arrays": {
            "default": {"max_abs": 0.2, "rmse_abs": 0.1, "p95_abs": 0.15, "p99_abs": 0.2},
            "by_id": {
                "grid.main": {"max_abs": 0.05, "rmse_abs": 0.03},
            },
        }
    }

    t_default = array_thresholds(profile, "other.grid")
    assert t_default["max_abs"] == 0.2
    assert t_default["rmse_abs"] == 0.1

    t_override = array_thresholds(profile, "grid.main")
    assert t_override["max_abs"] == 0.05
    assert t_override["rmse_abs"] == 0.03
    assert t_override["p95_abs"] == 0.15
    assert t_override["p99_abs"] == 0.2


def test_load_tolerance_file_repo_defaults() -> None:
    root = Path(__file__).resolve().parents[1]
    indoor = load_tolerance_file(root / "parity" / "tolerances" / "indoor_illuminance.yaml")
    ugr = load_tolerance_file(root / "parity" / "tolerances" / "ugr.yaml")

    assert isinstance(indoor, dict)
    assert isinstance(ugr, dict)
    assert "default" in indoor
    assert "default" in ugr
