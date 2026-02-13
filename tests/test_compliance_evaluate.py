from __future__ import annotations

from luxera.compliance.evaluate import evaluate_emergency, evaluate_indoor, evaluate_roadway


def test_evaluate_indoor_extracts_failures_and_explanations() -> None:
    out = evaluate_indoor(
        {
            "compliance_profile": {
                "status": "FAIL",
                "avg_ok": False,
                "avg_lux": 320.0,
                "target_avg_lux": 500.0,
                "uniformity_ok": True,
            }
        }
    )
    assert out.domain == "indoor"
    assert out.status == "FAIL"
    assert "avg_ok" in out.failed_checks
    assert any("actual=320.000" in line for line in out.explanations)


def test_evaluate_roadway_handles_uo_and_ti_checks() -> None:
    out = evaluate_roadway(
        {
            "compliance": {
                "status": "FAIL",
                "uo_ok": False,
                "uo": 0.32,
                "uo_min": 0.40,
                "ti_ok": False,
                "threshold_increment_ti_proxy_percent": 18.0,
                "ti_max_percent": 15.0,
            }
        }
    )
    assert out.domain == "roadway"
    assert out.status == "FAIL"
    assert "uo_ok" in out.failed_checks
    assert "ti_ok" in out.failed_checks


def test_evaluate_emergency_pass() -> None:
    out = evaluate_emergency(
        {
            "compliance": {
                "status": "PASS",
                "min_lux_ok": True,
                "uniformity_ok": True,
            }
        },
        standard="EN1838",
    )
    assert out.domain == "emergency"
    assert out.status == "PASS"
    assert out.failed_checks == []
