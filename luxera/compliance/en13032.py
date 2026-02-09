from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class EN13032Compliance:
    avg_illuminance: float
    uniformity_ratio: Optional[float]
    ugr_worst_case: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_illuminance": self.avg_illuminance,
            "uniformity_ratio": self.uniformity_ratio,
            "ugr_worst_case": self.ugr_worst_case,
        }


def evaluate_en13032(summary: Dict[str, Any]) -> EN13032Compliance:
    return EN13032Compliance(
        avg_illuminance=float(summary.get("mean_lux", summary.get("avg_illuminance", 0.0))),
        uniformity_ratio=summary.get("uniformity_ratio"),
        ugr_worst_case=summary.get("ugr_worst_case"),
    )
