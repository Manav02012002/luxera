from __future__ import annotations

from typing import List, Sequence, Tuple

from luxera.geometry.spatial import point_in_polygon

Point2 = Tuple[float, float]


def mask_points_by_polygons(points: Sequence[Point2], polygons: Sequence[Sequence[Point2]]) -> List[bool]:
    mask: List[bool] = []
    for p in points:
        blocked = False
        for poly in polygons:
            if len(poly) >= 3 and point_in_polygon((float(p[0]), float(p[1])), poly):
                blocked = True
                break
        mask.append(not blocked)
    return mask


def apply_obstacle_masks(base_mask: Sequence[bool], points: Sequence[Point2], obstacle_polygons: Sequence[Sequence[Point2]]) -> List[bool]:
    keep = mask_points_by_polygons(points, obstacle_polygons)
    n = min(len(base_mask), len(keep))
    out = [bool(base_mask[i] and keep[i]) for i in range(n)]
    if len(base_mask) > n:
        out.extend(bool(x) for x in base_mask[n:])
    return out
