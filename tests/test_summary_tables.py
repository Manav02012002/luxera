from __future__ import annotations

import numpy as np

from luxera.derived.summary_tables import aggregate_stats, grid_stats, to_csv


def test_grid_stats_and_aggregate() -> None:
    s1 = grid_stats(np.array([100.0, 200.0, 300.0]), spacing=0.5, area=4.0)
    s2 = grid_stats(np.array([50.0, 100.0]), spacing=1.0, area=2.0)
    agg = aggregate_stats([s1, s2])  # type: ignore[arg-type]
    assert s1["mean_lux"] == 200.0
    assert agg["global_worst_min_lux"] == 50.0
    assert agg["global_worst_uniformity_ratio"] >= 0.0


def test_to_csv_nonempty() -> None:
    txt = to_csv([{"id": "g1", "mean_lux": 123.0}])
    assert "id,mean_lux" in txt
    assert "g1,123.0" in txt
