from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping

import numpy as np

from luxera.metrics.core import compute_basic_metrics


@dataclass(frozen=True)
class GridResult:
    values: np.ndarray
    points_xyz: np.ndarray
    normal: tuple[float, float, float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    units: str = "lux"

    def finite_values(self) -> np.ndarray:
        arr = np.asarray(self.values, dtype=float).reshape(-1)
        return arr[np.isfinite(arr)]

    def to_summary(self) -> "SummaryResult":
        vals = self.finite_values()
        metrics = compute_basic_metrics(vals.tolist()).to_dict()
        return SummaryResult(metrics=metrics)


@dataclass(frozen=True)
class SummaryResult:
    metrics: Dict[str, float] = field(default_factory=dict)
    pass_fail: Dict[str, bool] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        out.update(self.metrics)
        if self.pass_fail:
            out["pass_fail"] = dict(self.pass_fail)
        if self.thresholds:
            out["thresholds"] = dict(self.thresholds)
        if self.notes:
            out["notes"] = list(self.notes)
        return out

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SummaryResult":
        base = dict(payload)
        metric_keys = {"E_avg", "E_min", "E_max", "U0", "U1", "P50", "P90", "mean_lux", "min_lux", "max_lux", "uniformity_ratio", "ugr_worst_case"}
        metrics = {k: float(v) for k, v in base.items() if k in metric_keys and isinstance(v, (int, float))}
        pass_fail = dict(base.get("pass_fail", {})) if isinstance(base.get("pass_fail"), Mapping) else {}
        thresholds = dict(base.get("thresholds", {})) if isinstance(base.get("thresholds"), Mapping) else {}
        notes_raw = base.get("notes")
        notes = [str(x) for x in notes_raw] if isinstance(notes_raw, Iterable) and not isinstance(notes_raw, (str, bytes)) else []
        return cls(metrics=metrics, pass_fail=pass_fail, thresholds=thresholds, notes=notes)
