from __future__ import annotations

from typing import List, Tuple

from luxera.models.derived import DerivedMetrics, Symmetry
from luxera.models.angles import AngleGrid
from luxera.models.candela import CandelaGrid


def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if p <= 0:
        return sorted_vals[0]
    if p >= 100:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def infer_symmetry(horizontal_deg: List[float]) -> Symmetry:
    # conservative inference based on typical LM-63 practice
    if len(horizontal_deg) == 1:
        return "FULL"
    hmin, hmax = horizontal_deg[0], horizontal_deg[-1]
    if abs(hmin - 0.0) < 1e-9 and abs(hmax - 90.0) < 1e-6:
        return "QUADRANT"
    if abs(hmin - 0.0) < 1e-9 and abs(hmax - 180.0) < 1e-6:
        return "BILATERAL"
    if abs(hmin - 0.0) < 1e-9 and abs(hmax - 360.0) < 1e-6:
        return "NONE"
    return "UNKNOWN"


def compute_derived_metrics(angles: AngleGrid, candela: CandelaGrid) -> DerivedMetrics:
    H = len(angles.horizontal_deg)
    V = len(angles.vertical_deg)

    # Find peak (scaled)
    peak = None
    peak_hv: Tuple[int, int] = (0, 0)
    for hi in range(H):
        for vi in range(V):
            val = candela.values_cd_scaled[hi][vi]
            if peak is None or val > peak:
                peak = val
                peak_hv = (hi, vi)

    peak_val = float(peak or 0.0)
    h_deg = angles.horizontal_deg[peak_hv[0]]
    v_deg = angles.vertical_deg[peak_hv[1]]

    all_vals = [x for row in candela.values_cd_scaled for x in row]
    all_sorted = sorted(all_vals)
    mean = sum(all_vals) / len(all_vals) if all_vals else 0.0
    p95 = _percentile(all_sorted, 95.0)

    stats = {
        "min": float(all_sorted[0] if all_sorted else 0.0),
        "max": float(all_sorted[-1] if all_sorted else 0.0),
        "mean": float(mean),
        "p95": float(p95),
    }

    angle_ranges = {
        "vmin": float(angles.vertical_deg[0]),
        "vmax": float(angles.vertical_deg[-1]),
        "hmin": float(angles.horizontal_deg[0]),
        "hmax": float(angles.horizontal_deg[-1]),
    }

    symmetry = infer_symmetry(angles.horizontal_deg)

    return DerivedMetrics(
        peak_candela=peak_val,
        peak_location=(float(h_deg), float(v_deg)),
        candela_stats=stats,
        symmetry_inferred=symmetry,
        angle_ranges=angle_ranges,
    )
