from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Optional, Tuple


Symmetry = Literal["FULL", "BILATERAL", "QUADRANT", "NONE", "UNKNOWN"]


@dataclass(frozen=True)
class DerivedMetrics:
    peak_candela: float
    peak_location: Tuple[float, float]  # (horizontal_deg, vertical_deg)
    candela_stats: Dict[str, float]     # min/max/mean/p95 (scaled)
    symmetry_inferred: Symmetry
    angle_ranges: Dict[str, float]      # vmin/vmax/hmin/hmax
