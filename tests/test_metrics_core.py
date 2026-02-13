from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from luxera.metrics.core import compute_basic_metrics, evaluate_thresholds


def test_metrics_basic_and_thresholds() -> None:
    values = [100.0, 80.0, 60.0, 40.0]
    m = compute_basic_metrics(values)
    assert m.E_avg == 70.0
    assert m.E_min == 40.0
    assert m.E_max == 100.0
    assert abs(m.U0 - (40.0 / 70.0)) < 1e-12
    assert abs(m.U1 - 0.4) < 1e-12
    ev = evaluate_thresholds({"E_avg_min": m.E_avg, "U0_min": m.U0}, {"E_avg_min": 50.0, "U0_min": 0.4})
    assert ev["status"] == "PASS"


def test_metrics_matches_golden_summary_box_room() -> None:
    csv_path = Path("tests/golden/expected/box_room/grid_g1.csv")
    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    vals = arr[:, 3].reshape(-1).tolist()
    m = compute_basic_metrics(vals)
    summary = json.loads(Path("tests/golden/expected/box_room/summary.json").read_text(encoding="utf-8"))
    assert abs(m.E_avg - float(summary["mean_lux"])) < 1e-6
    assert abs(m.E_min - float(summary["min_lux"])) < 1e-6
    assert abs(m.E_max - float(summary["max_lux"])) < 1e-6

