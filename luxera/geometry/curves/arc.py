from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

from luxera.geometry.tolerance import EPS_POS, EPS_WELD


Point2 = Tuple[float, float]


def _norm_angle(a: float) -> float:
    twopi = 2.0 * math.pi
    out = float(a) % twopi
    if out < 0.0:
        out += twopi
    return out


def _ccw_delta(a0: float, a1: float) -> float:
    d = _norm_angle(a1) - _norm_angle(a0)
    if d < 0.0:
        d += 2.0 * math.pi
    return d


@dataclass(frozen=True)
class Arc:
    center: Point2
    radius: float
    start_rad: float
    end_rad: float
    ccw: bool = True

    @staticmethod
    def from_bulge(start: Point2, end: Point2, bulge: float) -> "Arc":
        b = float(bulge)
        if abs(b) <= EPS_POS:
            raise ValueError("bulge cannot be zero for arc")
        x1, y1 = float(start[0]), float(start[1])
        x2, y2 = float(end[0]), float(end[1])
        chord = math.hypot(x2 - x1, y2 - y1)
        if chord <= EPS_POS:
            raise ValueError("bulge arc requires distinct endpoints")
        theta = 4.0 * math.atan(b)
        st = math.sin(theta * 0.5)
        if abs(st) <= EPS_POS:
            raise ValueError("invalid bulge angle")
        radius = abs(chord / (2.0 * st))

        mx, my = (x1 + x2) * 0.5, (y1 + y2) * 0.5
        dx, dy = (x2 - x1), (y2 - y1)
        nx, ny = -dy, dx
        ln = math.hypot(nx, ny)
        nx, ny = nx / ln, ny / ln
        d = math.sqrt(max(radius * radius - (chord * 0.5) * (chord * 0.5), 0.0))
        sign = 1.0 if b > 0.0 else -1.0
        cx, cy = mx + sign * d * nx, my + sign * d * ny

        a0 = math.atan2(y1 - cy, x1 - cx)
        a1 = math.atan2(y2 - cy, x2 - cx)
        return Arc(center=(cx, cy), radius=radius, start_rad=a0, end_rad=a1, ccw=(b > 0.0))

    @property
    def start_point(self) -> Point2:
        return (
            float(self.center[0] + self.radius * math.cos(self.start_rad)),
            float(self.center[1] + self.radius * math.sin(self.start_rad)),
        )

    @property
    def end_point(self) -> Point2:
        return (
            float(self.center[0] + self.radius * math.cos(self.end_rad)),
            float(self.center[1] + self.radius * math.sin(self.end_rad)),
        )

    def sweep(self) -> float:
        if self.ccw:
            return _ccw_delta(self.start_rad, self.end_rad)
        return _ccw_delta(self.end_rad, self.start_rad)

    def contains_angle(self, a: float, eps: float = EPS_WELD) -> bool:
        ang = _norm_angle(a)
        if self.ccw:
            d = _ccw_delta(self.start_rad, ang)
            return d <= self.sweep() + eps
        d = _ccw_delta(self.end_rad, ang)
        return d <= self.sweep() + eps

    def point_at(self, t: float) -> Point2:
        tt = min(1.0, max(0.0, float(t)))
        sw = self.sweep()
        a = self.start_rad + sw * tt if self.ccw else self.start_rad - sw * tt
        return (
            float(self.center[0] + self.radius * math.cos(a)),
            float(self.center[1] + self.radius * math.sin(a)),
        )

    def nearest_point(self, p: Point2) -> Point2:
        px, py = float(p[0]), float(p[1])
        cx, cy = float(self.center[0]), float(self.center[1])
        vx, vy = px - cx, py - cy
        lv = math.hypot(vx, vy)
        if lv <= EPS_POS:
            cands = [self.start_point, self.end_point]
            return min(cands, key=lambda q: (q[0] - px) * (q[0] - px) + (q[1] - py) * (q[1] - py))
        ang = math.atan2(vy, vx)
        on_circle = (cx + self.radius * math.cos(ang), cy + self.radius * math.sin(ang))
        if self.contains_angle(ang):
            return (float(on_circle[0]), float(on_circle[1]))
        cands = [self.start_point, self.end_point]
        return min(cands, key=lambda q: (q[0] - px) * (q[0] - px) + (q[1] - py) * (q[1] - py))

    def intersections_with_line_segment(self, a: Point2, b: Point2, eps: float = EPS_WELD) -> List[Point2]:
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        cx, cy = float(self.center[0]), float(self.center[1])
        dx, dy = bx - ax, by - ay
        fx, fy = ax - cx, ay - cy

        A = dx * dx + dy * dy
        if A <= EPS_POS:
            return []
        B = 2.0 * (fx * dx + fy * dy)
        C = fx * fx + fy * fy - self.radius * self.radius
        disc = B * B - 4.0 * A * C
        if disc < -eps:
            return []
        disc = max(0.0, disc)
        s = math.sqrt(disc)
        ts = [(-B - s) / (2.0 * A), (-B + s) / (2.0 * A)]
        out: List[Point2] = []
        for t in ts:
            if t < -eps or t > 1.0 + eps:
                continue
            t = min(1.0, max(0.0, t))
            x, y = ax + dx * t, ay + dy * t
            ang = math.atan2(y - cy, x - cx)
            if self.contains_angle(ang, eps=eps):
                out.append((float(x), float(y)))
        # dedupe
        ded: List[Point2] = []
        for p in out:
            if not any(math.hypot(p[0] - q[0], p[1] - q[1]) <= eps for q in ded):
                ded.append(p)
        return ded

    def intersections_with_arc(self, other: "Arc", eps: float = EPS_WELD) -> List[Point2]:
        x0, y0 = float(self.center[0]), float(self.center[1])
        x1, y1 = float(other.center[0]), float(other.center[1])
        r0, r1 = float(self.radius), float(other.radius)
        dx, dy = x1 - x0, y1 - y0
        d = math.hypot(dx, dy)
        if d <= EPS_POS:
            return []
        if d > r0 + r1 + eps:
            return []
        if d < abs(r0 - r1) - eps:
            return []

        a = (r0 * r0 - r1 * r1 + d * d) / (2.0 * d)
        h2 = r0 * r0 - a * a
        if h2 < -eps:
            return []
        h = math.sqrt(max(0.0, h2))
        xm = x0 + a * dx / d
        ym = y0 + a * dy / d
        rx = -dy * (h / d)
        ry = dx * (h / d)
        pts = [(xm + rx, ym + ry), (xm - rx, ym - ry)]

        out: List[Point2] = []
        for x, y in pts:
            a0 = math.atan2(y - y0, x - x0)
            a1 = math.atan2(y - y1, x - x1)
            if self.contains_angle(a0, eps=eps) and other.contains_angle(a1, eps=eps):
                p = (float(x), float(y))
                if not any(math.hypot(p[0] - q[0], p[1] - q[1]) <= eps for q in out):
                    out.append(p)
        return out
