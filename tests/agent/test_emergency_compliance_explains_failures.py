from __future__ import annotations

from luxera.compliance.evaluate import evaluate_emergency


def test_emergency_evaluator_explains_threshold_failures() -> None:
    out = evaluate_emergency(
        {
            "compliance": {
                "status": "FAIL",
                "route_pass": False,
                "route_min_lux": 0.7,
                "route_min_lux_target": 1.0,
                "open_area_pass": False,
            }
        },
        standard="EN1838",
    )
    assert out.status == "FAIL"
    assert out.explanations
    joined = "\n".join(out.explanations)
    assert "actual=0.700" in joined
    assert "threshold" in joined
