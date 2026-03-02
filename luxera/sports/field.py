from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class PlayingField:
    sport: str
    length: float
    width: float
    run_off: float
    orientation_deg: float

    @property
    def total_length(self) -> float:
        return self.length + 2.0 * self.run_off

    @property
    def total_width(self) -> float:
        return self.width + 2.0 * self.run_off


STANDARD_FIELDS: Dict[str, PlayingField] = {
    "football_fifa": PlayingField("football", 105.0, 68.0, 5.0, 0.0),
    "tennis_singles": PlayingField("tennis", 23.77, 8.23, 3.66, 0.0),
    "tennis_doubles": PlayingField("tennis", 23.77, 10.97, 3.66, 0.0),
    "athletics_400m": PlayingField("athletics", 176.9, 92.5, 5.0, 0.0),
    "rugby_union": PlayingField("rugby", 100.0, 70.0, 5.0, 0.0),
    "hockey_field": PlayingField("hockey", 91.4, 55.0, 5.0, 0.0),
    "basketball_fiba": PlayingField("basketball", 28.0, 15.0, 2.0, 0.0),
    "volleyball_indoor": PlayingField("volleyball", 18.0, 9.0, 3.0, 0.0),
    "swimming_50m": PlayingField("swimming", 50.0, 25.0, 3.0, 0.0),
    "cricket_oval": PlayingField("cricket", 150.0, 130.0, 10.0, 0.0),
    "baseball_diamond": PlayingField("baseball", 120.0, 120.0, 8.0, 0.0),
}

