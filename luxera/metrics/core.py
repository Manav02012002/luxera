from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class BasicMetrics:
    E_avg: float
    E_min: float
    E_max: float
    U0: float
    U1: float
    P50: float
    P90: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "E_avg": self.E_avg,
            "E_min": self.E_min,
            "E_max": self.E_max,
            "U0": self.U0,
            "U1": self.U1,
            "P50": self.P50,
            "P90": self.P90,
        }


def compute_basic_metrics(values: Iterable[float]) -> BasicMetrics:
    arr = np.asarray(list(values), dtype=float).reshape(-1)
    if arr.size == 0:
        return BasicMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return BasicMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    e_avg = float(np.mean(arr))
    e_min = float(np.min(arr))
    e_max = float(np.max(arr))
    u0 = (e_min / e_avg) if e_avg > 1e-12 else 0.0
    u1 = (e_min / e_max) if e_max > 1e-12 else 0.0
    return BasicMetrics(
        E_avg=e_avg,
        E_min=e_min,
        E_max=e_max,
        U0=u0,
        U1=u1,
        P50=float(np.percentile(arr, 50.0)),
        P90=float(np.percentile(arr, 90.0)),
    )


def evaluate_thresholds(metrics: Mapping[str, float], thresholds: Mapping[str, float]) -> Dict[str, object]:
    checks: Dict[str, bool] = {}
    reasons = []
    for key, limit in thresholds.items():
        v = float(metrics.get(key, 0.0))
        if key.lower().endswith("_max"):
            ok = v <= float(limit)
        else:
            ok = v >= float(limit)
        checks[key] = bool(ok)
        reasons.append(f"{key}={'PASS' if ok else 'FAIL'} ({v:.3f} vs {float(limit):.3f})")
    status = "PASS" if all(checks.values()) else "FAIL"
    return {"status": status, "checks": checks, "reasons": reasons, "thresholds": dict(thresholds)}
