from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from luxera.parity.expected import compare_expected, compare_results_to_expected, validate_expected_payload


def test_validate_expected_payload_accepts_valid_schema() -> None:
    payload = {
        "schema_version": "parity_expected_v1",
        "tolerances": {
            "default": {"abs": 1e-6, "rel": 1e-6},
            "metrics": {"engines.a.summary.mean_lux": {"abs": 1e-3, "rel": 1e-3}},
        },
        "ignore": ["engines.a.summary.calc_objects"],
        "expected": {
            "pack_name": "demo",
            "engines": {
                "a": {
                    "job_id": "job_a",
                    "job_type": "direct",
                    "backend": "cpu",
                    "summary": {"mean_lux": 12.0},
                }
            },
        },
    }
    validated = validate_expected_payload(payload)
    assert validated["schema_version"] == "parity_expected_v1"
    assert validated["tolerances"]["default"]["abs"] == pytest.approx(1e-6)


def test_validate_expected_payload_rejects_invalid_default_tolerance() -> None:
    payload = {
        "schema_version": "parity_expected_v1",
        "tolerances": {"default": {"abs": 1e-6}},
        "expected": {},
    }
    with pytest.raises(ValueError, match="abs and rel"):
        validate_expected_payload(payload)


def test_validate_expected_payload_rejects_invalid_ignore_type() -> None:
    payload = {
        "schema_version": "parity_expected_v1",
        "tolerances": {"default": {"abs": 1e-6, "rel": 1e-6}},
        "ignore": "engines.a.summary.mean_lux",
        "expected": {},
    }
    with pytest.raises(ValueError, match="list of strings"):
        validate_expected_payload(payload)


def test_validate_expected_v2_success() -> None:
    payload = {
        "schema_version": "parity_expected_v2",
        "scene_id": "office_01",
        "baseline": "luxera",
        "baseline_version": "v1",
        "generated_by": {"tool": "pytest", "version": "1"},
        "results": {
            "mean_lux": 123.4,
            "max_lux": 456.7,
        },
        "tags": ["indoor", "fast"],
    }
    validated = validate_expected_payload(payload)
    assert validated["schema_version"] == "parity_expected_v2"
    assert validated["scene_id"] == "office_01"
    assert validated["results"]["mean_lux"] == pytest.approx(123.4)


def test_validate_expected_v2_missing_required_fields() -> None:
    payload = {
        "schema_version": "parity_expected_v2",
        "scene_id": "office_01",
        "baseline": "luxera",
        "results": {"mean_lux": 100.0},
        "global": {"deterministic": True},
    }
    with pytest.raises(ValueError, match="baseline_version"):
        validate_expected_payload(payload)


def test_compare_expected_keeps_v1_behavior() -> None:
    expected_v1 = {
        "schema_version": "parity_expected_v1",
        "tolerances": {
            "default": {"abs": 1e-6, "rel": 1e-6},
            "metrics": {"engines.a.summary.mean_lux": {"abs": 1e-3, "rel": 1e-3}},
        },
        "ignore": [],
        "expected": {
            "pack_name": "demo",
            "engines": {
                "a": {
                    "job_id": "job_a",
                    "job_type": "direct",
                    "backend": "cpu",
                    "summary": {"mean_lux": 100.0},
                }
            },
        },
    }
    actual = {
        "pack_name": "demo",
        "engines": {
            "a": {
                "job_id": "job_a",
                "job_type": "direct",
                "backend": "cpu",
                "summary": {"mean_lux": 100.0005},
            }
        },
    }

    validated_v1 = validate_expected_payload(expected_v1)
    cmp_old = compare_results_to_expected(actual, validated_v1)
    cmp_new = compare_expected(actual, expected_v1, tolerance_model=None, scene_tags=[])
    assert cmp_old.passed
    assert cmp_new.passed
    assert cmp_old.checked_metrics == cmp_new.checked_metrics
    assert cmp_old.mismatches == cmp_new.mismatches


def test_compare_expected_v2_default_tolerance_and_override() -> None:
    expected_v2 = {
        "schema_version": "parity_expected_v2",
        "scene_id": "office_01",
        "baseline": "luxera",
        "baseline_version": "v1",
        "results": {
            "mean_lux": 100.0,
            "max_lux": 200.0,
        },
    }
    actual = {
        "results": {
            "mean_lux": 100.0005,
            "max_lux": 200.2,
        }
    }

    cmp_default = compare_expected(actual, expected_v2, tolerance_model=None, scene_tags=["indoor"])
    # With profile-based defaults from parity/tolerances/indoor_illuminance.yaml these values pass.
    assert cmp_default.passed

    cmp_relaxed = compare_expected(
        actual,
        expected_v2,
        tolerance_model={
            "default": {"abs": 1e-3, "rel": 1e-3},
            "metrics": {"max_lux": {"abs": 0.05, "rel": 0.0}},
        },
        scene_tags=["indoor"],
    )
    assert not cmp_relaxed.passed
    assert any(m.path == "max_lux" for m in cmp_relaxed.mismatches)


def _grid_hash_for_test(rows: list[list[float]]) -> str:
    import numpy as np

    arr = np.asarray(rows, dtype=float)
    hasher = hashlib.sha256()
    hasher.update(str(tuple(int(x) for x in arr.shape)).encode("utf-8"))
    hasher.update(arr.tobytes(order="C"))
    return f"sha256:{hasher.hexdigest()}"


def test_compare_expected_v2_grid_values_stats(tmp_path: Path) -> None:
    expected_grid = [[10.0, 11.0], [12.0, 13.0]]
    expected_hash = _grid_hash_for_test(expected_grid)
    sidecar = tmp_path / "grid.csv"
    sidecar.write_text("10,11\n12,13\n", encoding="utf-8")

    expected_v2 = {
        "schema_version": "parity_expected_v2",
        "scene_id": "office_01",
        "baseline": "luxera",
        "baseline_version": "v1",
        "results": {
            "workplane_grid": {
                "grid_1": {
                    "grid_values_lux": {
                        "shape": [2, 2],
                        "hash": expected_hash,
                        "summary": {},
                        "sidecar": "grid.csv",
                    }
                }
            }
        },
    }
    actual = {
        "results": {
            "workplane_grid": {
                "grid_1": {
                    "grid_values_lux": [[10.0, 11.01], [12.0, 12.99]],
                }
            }
        }
    }

    cmp_pass = compare_expected(
        actual,
        expected_v2,
        tolerance_model={"arrays": {"default": {"max_abs": 0.02, "rmse": 0.02, "mean_abs": 0.02, "p95_abs": 0.02, "p99_abs": 0.02}}},
        expected_root=tmp_path,
    )
    assert cmp_pass.passed

    cmp_fail = compare_expected(
        actual,
        expected_v2,
        tolerance_model={"arrays": {"default": {"max_abs": 0.001, "rmse": 0.001, "mean_abs": 0.001, "p95_abs": 0.001, "p99_abs": 0.001}}},
        expected_root=tmp_path,
    )
    assert not cmp_fail.passed
    assert any(m.reason == "array_mismatch" for m in cmp_fail.mismatches)
