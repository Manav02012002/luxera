from __future__ import annotations

from luxera.metrics.emergency.en1838 import evaluate_en1838
from luxera.metrics.standards.en12464 import evaluate_en12464


def test_en12464_metrics_eval() -> None:
    out = evaluate_en12464([500.0, 450.0, 550.0], thresholds={"E_avg_min": 300.0, "U0_min": 0.4})
    assert out["metrics"]["E_avg"] > 0
    assert out["compliance"]["status"] == "PASS"


def test_en1838_metrics_eval() -> None:
    out = evaluate_en1838([2.0, 1.5, 1.2], thresholds={"E_min_min": 1.0, "U0_min": 0.1})
    assert out["metrics"]["E_min"] >= 1.2
    assert out["compliance"]["status"] == "PASS"

