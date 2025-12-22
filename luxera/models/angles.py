from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class AngleGrid:
    vertical_deg: List[float]
    horizontal_deg: List[float]
    vertical_line_span: Tuple[int, int]    # (start_line_no, end_line_no), inclusive
    horizontal_line_span: Tuple[int, int]  # (start_line_no, end_line_no), inclusive
