from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from luxera.geometry.zones import resolve_zone_polygon
from luxera.metrics.core import compute_basic_metrics
from luxera.project.schema import RoomSpec, ZoneSpec

Point2 = Tuple[float, float]


def point_in_polygon_inclusive(point: Point2, polygon: Sequence[Point2], eps: float = 1e-9) -> bool:
    x = float(point[0])
    y = float(point[1])
    n = len(polygon)
    if n < 3:
        return False

    for i in range(n):
        x1, y1 = float(polygon[i][0]), float(polygon[i][1])
        x2, y2 = float(polygon[(i + 1) % n][0]), float(polygon[(i + 1) % n][1])
        minx, maxx = min(x1, x2) - eps, max(x1, x2) + eps
        miny, maxy = min(y1, y2) - eps, max(y1, y2) + eps
        if x < minx or x > maxx or y < miny or y > maxy:
            continue
        dx = x2 - x1
        dy = y2 - y1
        cross = (x - x1) * dy - (y - y1) * dx
        if abs(cross) <= eps:
            return True

    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(polygon[i][0]), float(polygon[i][1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        crosses = (yi > y) != (yj > y)
        if crosses:
            x_intersect = (xj - xi) * (y - yi) / max(yj - yi, eps) + xi
            if x <= x_intersect + eps:
                inside = not inside
        j = i
    return inside


def _zone_class(tags: Iterable[str]) -> str:
    lowered = {str(t).strip().lower() for t in tags}
    if "task_area" in lowered or "task" in lowered:
        return "task_area"
    if "surrounding_area" in lowered or "surrounding" in lowered:
        return "surrounding_area"
    return "custom"


def _req_float(req: Mapping[str, object], *keys: str) -> Optional[float]:
    for k in keys:
        if k in req and isinstance(req.get(k), (int, float)):
            return float(req[k])  # type: ignore[index]
    return None


def compute_zone_metrics(
    calc_objects: Sequence[Mapping[str, object]],
    zones: Sequence[ZoneSpec],
    rooms_by_id: Mapping[str, RoomSpec],
    zone_requirements: Optional[Mapping[str, Mapping[str, object]]] = None,
    maintenance_factor: float = 1.0,
) -> List[Dict[str, object]]:
    req_map = zone_requirements or {}
    rows: List[Dict[str, object]] = []

    ordered_objects = sorted(
        [o for o in calc_objects if isinstance(o, Mapping)],
        key=lambda o: (str(o.get("type", "")), str(o.get("id", ""))),
    )
    ordered_zones = sorted(list(zones), key=lambda z: str(z.id))

    for zone in ordered_zones:
        try:
            polygon = resolve_zone_polygon(zone, dict(rooms_by_id))
        except Exception:
            continue
        if len(polygon) < 3:
            continue

        req = req_map.get(str(zone.id), {})
        target_ids = {str(v) for v in req.get("target_ids", [])} if isinstance(req.get("target_ids"), list) else set()
        allowed_types = (
            {str(v) for v in req.get("object_types", [])}
            if isinstance(req.get("object_types"), list) and req.get("object_types")
            else {"grid"}
        )

        selected_values: List[float] = []
        selected_points = 0
        target_count = 0
        for obj in ordered_objects:
            obj_id = str(obj.get("id", ""))
            obj_type = str(obj.get("type", ""))
            if obj_type not in allowed_types:
                continue
            if target_ids and obj_id not in target_ids:
                continue
            pts = obj.get("points")
            vals = obj.get("values")
            if not isinstance(pts, np.ndarray) or not isinstance(vals, np.ndarray):
                continue
            points = np.asarray(pts, dtype=float).reshape(-1, 3)
            values = np.asarray(vals, dtype=float).reshape(-1)
            if points.shape[0] != values.shape[0]:
                continue
            target_count += 1
            for i in range(points.shape[0]):
                if not np.isfinite(values[i]):
                    continue
                if point_in_polygon_inclusive((float(points[i, 0]), float(points[i, 1])), polygon):
                    selected_values.append(float(values[i]))
                    selected_points += 1

        mf = float(maintenance_factor)
        if mf < 0.0:
            mf = 0.0
        selected_values = [float(v) * mf for v in selected_values]

        metrics = compute_basic_metrics(selected_values).to_dict() if selected_values else {
            "E_avg": 0.0,
            "E_min": 0.0,
            "E_max": 0.0,
            "U0": 0.0,
            "U1": 0.0,
            "P50": 0.0,
            "P90": 0.0,
        }
        eavg = float(metrics.get("E_avg", 0.0))
        emin = float(metrics.get("E_min", 0.0))
        u0 = float(metrics.get("U0", 0.0))

        eavg_min = _req_float(req, "Eavg_min", "E_avg_min", "eavg_min")
        emin_min = _req_float(req, "Emin_min", "E_min_min", "emin_min")
        u0_min = _req_float(req, "U0_min", "u0_min")

        checks: List[Dict[str, object]] = []
        for metric_name, actual, threshold in (
            ("Eavg", eavg, eavg_min),
            ("Emin", emin, emin_min),
            ("U0", u0, u0_min),
        ):
            if threshold is None:
                continue
            checks.append(
                {
                    "metric": metric_name,
                    "comparator": ">=",
                    "actual": actual,
                    "target": float(threshold),
                    "pass": bool(actual >= float(threshold)),
                    "margin": float(actual - float(threshold)),
                }
            )

        status = "N/A" if not checks else ("PASS" if all(bool(c["pass"]) for c in checks) else "FAIL")
        rows.append(
            {
                "zone_id": str(zone.id),
                "zone_name": str(zone.name),
                "zone_class": _zone_class(getattr(zone, "tags", [])),
                "target_count": int(target_count),
                "point_count": int(selected_points),
                "Eavg": eavg,
                "Emin": emin,
                "U0": u0,
                "requirements": {k: v for k, v in {"Eavg_min": eavg_min, "Emin_min": emin_min, "U0_min": u0_min}.items() if v is not None},
                "checks": checks,
                "status": status,
            }
        )

    return rows
