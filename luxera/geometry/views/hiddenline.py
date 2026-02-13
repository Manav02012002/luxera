from __future__ import annotations

from typing import List, Sequence

from luxera.geometry.views.project import DrawingPrimitive


def depth_sort_primitives(primitives: Sequence[DrawingPrimitive], *, back_to_front: bool = True) -> List[DrawingPrimitive]:
    """Minimum viable hidden-line ordering by average primitive depth."""
    out = list(primitives)
    out.sort(key=lambda p: (float(p.depth), p.layer, p.style, len(p.points)), reverse=bool(back_to_front))
    return out
