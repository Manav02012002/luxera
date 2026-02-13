from __future__ import annotations

from typing import Iterable, List, Sequence, Set, Tuple

Point2 = Tuple[float, float]


def _idx(i: int, j: int, nx: int) -> int:
    return j * nx + i


def _cell_gradient(values: Sequence[float], nx: int, ny: int, i: int, j: int) -> float:
    if i < 0 or j < 0 or i >= nx - 1 or j >= ny - 1:
        return 0.0
    corners = [
        float(values[_idx(i, j, nx)]),
        float(values[_idx(i + 1, j, nx)]),
        float(values[_idx(i + 1, j + 1, nx)]),
        float(values[_idx(i, j + 1, nx)]),
    ]
    return max(corners) - min(corners)


def refine_rect_grid(
    *,
    origin: Point2,
    width: float,
    height: float,
    nx: int,
    ny: int,
    values: Sequence[float],
    gradient_threshold: float,
) -> List[Point2]:
    if nx < 2 or ny < 2:
        raise ValueError("nx and ny must be >= 2")
    if len(values) != nx * ny:
        raise ValueError("values must have length nx*ny")
    if gradient_threshold < 0.0:
        raise ValueError("gradient_threshold must be >= 0")

    ox, oy = float(origin[0]), float(origin[1])
    dx = float(width) / float(nx - 1)
    dy = float(height) / float(ny - 1)

    points: Set[Point2] = set()
    for j in range(ny):
        for i in range(nx):
            points.add((ox + i * dx, oy + j * dy))

    for j in range(ny - 1):
        for i in range(nx - 1):
            g = _cell_gradient(values, nx, ny, i, j)
            if g < float(gradient_threshold):
                continue
            x0 = ox + i * dx
            y0 = oy + j * dy
            x1 = x0 + dx
            y1 = y0 + dy
            xm = 0.5 * (x0 + x1)
            ym = 0.5 * (y0 + y1)
            points.update(
                {
                    (xm, ym),
                    (xm, y0),
                    (xm, y1),
                    (x0, ym),
                    (x1, ym),
                }
            )

    return sorted(points)


def refine_from_samples(
    points_xy: Sequence[Point2],
    values: Sequence[float],
    *,
    neighborhood_radius: float,
    gradient_threshold: float,
) -> List[Point2]:
    if len(points_xy) != len(values):
        raise ValueError("points_xy and values must have the same length")
    r2 = float(neighborhood_radius) * float(neighborhood_radius)
    out: List[Point2] = []
    for i, p in enumerate(points_xy):
        pi = (float(p[0]), float(p[1]))
        vi = float(values[i])
        keep = False
        for j, q in enumerate(points_xy):
            if i == j:
                continue
            dx = float(q[0]) - pi[0]
            dy = float(q[1]) - pi[1]
            if dx * dx + dy * dy > r2:
                continue
            if abs(float(values[j]) - vi) >= float(gradient_threshold):
                keep = True
                break
        if keep:
            out.append(pi)
    return out
