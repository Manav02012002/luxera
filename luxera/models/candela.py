from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class CandelaGrid:
    # Shape: [H][V] where H = len(horizontal angles), V = len(vertical angles)
    values_cd: List[List[float]]           # raw as in file
    values_cd_scaled: List[List[float]]    # multiplied by candela multiplier
    line_span: Tuple[int, int]             # (start_line_no, end_line_no), inclusive

    min_cd: float
    max_cd: float
    has_negative: bool
    has_nan_or_inf: bool
