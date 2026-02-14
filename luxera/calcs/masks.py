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


def apply_opening_proximity_mask(
    base_mask: Sequence[bool],
    points: Sequence[Point2],
    opening_polygons: Sequence[Sequence[Point2]],
    margin: float,
) -> List[bool]:
    m = max(0.0, float(margin))
    if m <= 0.0 or not opening_polygons:
        return [bool(x) for x in base_mask]
    bboxes: List[Tuple[float, float, float, float]] = []
    for poly in opening_polygons:
        if len(poly) < 2:
            continue
        xs = [float(p[0]) for p in poly]
        ys = [float(p[1]) for p in poly]
        bboxes.append((min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m))
    if not bboxes:
        return [bool(x) for x in base_mask]
    out: List[bool] = []
    for i, p in enumerate(points):
        keep = bool(base_mask[i]) if i < len(base_mask) else True
        if keep:
            x, y = float(p[0]), float(p[1])
            for x0, y0, x1, y1 in bboxes:
                if x0 <= x <= x1 and y0 <= y <= y1:
                    keep = False
                    break
        out.append(keep)
    return out
