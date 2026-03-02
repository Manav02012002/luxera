from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class SportStandard:
    sport: str
    class_level: str
    E_h_maintained: float
    E_h_uniformity_U1: float
    E_h_uniformity_U2: float
    E_v_maintained: Optional[float]
    E_v_uniformity: Optional[float]
    GR_max: Optional[float]
    description: str


def _std(
    sport: str,
    cls: str,
    eh: float,
    u1: float,
    u2: float,
    ev: Optional[float],
    evu: Optional[float],
    gr: Optional[float],
    desc: str,
) -> SportStandard:
    return SportStandard(sport, cls, eh, u1, u2, ev, evu, gr, desc)


# Practical EN 12193-aligned targets used in industry workflows.
SPORT_STANDARDS: Dict[str, Dict[str, SportStandard]] = {
    "football": {
        "I": _std("football", "I", 500, 0.7, 0.6, 1000, 0.4, 50, "International competition"),
        "II": _std("football", "II", 300, 0.6, 0.5, 500, 0.3, 50, "National competition"),
        "III": _std("football", "III", 200, 0.5, 0.4, None, None, 55, "Local/training"),
    },
    "tennis": {
        "I": _std("tennis", "I", 750, 0.7, 0.6, 1000, 0.5, 50, "International TV competition"),
        "II": _std("tennis", "II", 500, 0.6, 0.5, 500, 0.4, 50, "National competition"),
        "III": _std("tennis", "III", 300, 0.5, 0.4, None, None, 55, "Club/recreational"),
    },
    "athletics": {
        "I": _std("athletics", "I", 500, 0.7, 0.6, 1000, 0.5, 50, "International broadcast"),
        "II": _std("athletics", "II", 300, 0.6, 0.5, 600, 0.4, 50, "National competition"),
        "III": _std("athletics", "III", 200, 0.5, 0.4, None, None, 55, "Training/local"),
    },
    "rugby": {
        "I": _std("rugby", "I", 500, 0.7, 0.6, 1000, 0.4, 50, "International competition"),
        "II": _std("rugby", "II", 300, 0.6, 0.5, 500, 0.3, 50, "National competition"),
        "III": _std("rugby", "III", 200, 0.5, 0.4, None, None, 55, "Local/training"),
    },
    "hockey": {
        "I": _std("hockey", "I", 500, 0.7, 0.6, 1000, 0.5, 50, "International competition"),
        "II": _std("hockey", "II", 350, 0.6, 0.5, 600, 0.4, 50, "National competition"),
        "III": _std("hockey", "III", 250, 0.5, 0.4, None, None, 55, "Local/training"),
    },
    "basketball": {
        "I": _std("basketball", "I", 750, 0.7, 0.6, 1000, 0.5, 50, "International TV competition"),
        "II": _std("basketball", "II", 500, 0.6, 0.5, 750, 0.4, 50, "National competition"),
        "III": _std("basketball", "III", 300, 0.5, 0.4, None, None, 55, "Club/recreational"),
    },
    "volleyball": {
        "I": _std("volleyball", "I", 750, 0.7, 0.6, 1000, 0.5, 50, "International TV competition"),
        "II": _std("volleyball", "II", 500, 0.6, 0.5, 750, 0.4, 50, "National competition"),
        "III": _std("volleyball", "III", 300, 0.5, 0.4, None, None, 55, "Club/recreational"),
    },
    "swimming": {
        "I": _std("swimming", "I", 500, 0.7, 0.6, 1000, 0.5, 50, "International competition"),
        "II": _std("swimming", "II", 300, 0.6, 0.5, 600, 0.4, 50, "National competition"),
        "III": _std("swimming", "III", 200, 0.5, 0.4, None, None, 55, "Training/local"),
    },
    "cricket": {
        "I": _std("cricket", "I", 750, 0.7, 0.6, 1500, 0.5, 50, "International TV competition"),
        "II": _std("cricket", "II", 500, 0.6, 0.5, 1000, 0.4, 50, "National competition"),
        "III": _std("cricket", "III", 300, 0.5, 0.4, None, None, 55, "Club/recreational"),
    },
    "baseball": {
        "I": _std("baseball", "I", 500, 0.7, 0.6, 1000, 0.5, 50, "International competition"),
        "II": _std("baseball", "II", 300, 0.6, 0.5, 750, 0.4, 50, "National competition"),
        "III": _std("baseball", "III", 200, 0.5, 0.4, None, None, 55, "Local/training"),
    },
}

