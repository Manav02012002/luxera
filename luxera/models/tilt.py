from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class TiltData:
    angles_deg: List[float]
    factors: List[float]

    def validate(self) -> None:
        if not self.angles_deg or not self.factors:
            raise ValueError("Tilt data must not be empty")
        if len(self.angles_deg) != len(self.factors):
            raise ValueError("Tilt angles/factors length mismatch")
        if any(self.angles_deg[i] >= self.angles_deg[i + 1] for i in range(len(self.angles_deg) - 1)):
            raise ValueError("Tilt angles must be strictly increasing")
        if any(f <= 0.0 for f in self.factors):
            raise ValueError("Tilt factors must be positive")

    def interpolate(self, angle_deg: float) -> float:
        self.validate()
        a = float(angle_deg)
        if a <= self.angles_deg[0]:
            return float(self.factors[0])
        if a >= self.angles_deg[-1]:
            return float(self.factors[-1])
        for i in range(len(self.angles_deg) - 1):
            lo = self.angles_deg[i]
            hi = self.angles_deg[i + 1]
            if lo <= a <= hi:
                t = (a - lo) / max(hi - lo, 1e-12)
                return float(self.factors[i] * (1.0 - t) + self.factors[i + 1] * t)
        return float(self.factors[-1])
