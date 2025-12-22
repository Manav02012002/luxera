from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PhotometryHeader:
    num_lamps: int
    lumens_per_lamp: float
    candela_multiplier: float
    num_vertical_angles: int
    num_horizontal_angles: int
    photometric_type: Literal[1, 2, 3]   # 1=C, 2=B, 3=A
    units_type: Literal[1, 2]            # 1=feet, 2=meters
    width: float
    length: float
    height: float
    line_no: int                         # 1-indexed
