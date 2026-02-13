from __future__ import annotations

from typing import Dict, Iterable, Mapping

from luxera.metrics.core import compute_basic_metrics, evaluate_thresholds


def evaluate_en1838(values: Iterable[float], thresholds: Mapping[str, float] | None = None) -> Dict[str, object]:
    m = compute_basic_metrics(values)
    metrics = m.to_dict()
    mapped = {
        "E_min_min": float(metrics["E_min"]),
        "U0_min": float(metrics["U0"]),
    }
    th = dict(thresholds or {})
    return {
        "metrics": metrics,
        "compliance": evaluate_thresholds(mapped, th) if th else {"status": "UNKNOWN", "checks": {}, "reasons": []},
    }

