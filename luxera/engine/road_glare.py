from __future__ import annotations
"""Contract: docs/spec/roadway_glare.md."""

import math
from typing import Dict, List, Sequence, Tuple

from luxera.calculation.illuminance import Luminaire
from luxera.geometry.core import Vector3
from luxera.photometry.sample import sample_intensity_cd_world


def _safe_view_dir(settings: Dict[str, object]) -> Tuple[float, float, float]:
    raw = settings.get("glare_view_dir", (1.0, 0.0, 0.0))
    if isinstance(raw, (list, tuple)) and len(raw) == 3:
        x, y, z = float(raw[0]), float(raw[1]), float(raw[2])
    else:
        x, y, z = 1.0, 0.0, 0.0
    n = math.sqrt(x * x + y * y + z * z)
    if n <= 1e-12:
        return (1.0, 0.0, 0.0)
    return (x / n, y / n, z / n)


def compute_observer_glare_metrics(
    observers: Sequence[Dict[str, float | str]],
    luminaires: Sequence[Luminaire],
    *,
    lavg_reference_cd_m2: float,
    settings: Dict[str, object],
) -> tuple[List[Dict[str, object]], Dict[str, object]]:
    method = str(settings.get("glare_method", "rp8_veiling_ratio")).strip().lower()
    theta_min_deg = float(settings.get("glare_theta_min_deg", 0.2))
    theta_max_deg = float(settings.get("glare_theta_max_deg", 85.0))
    rp8_k = float(settings.get("rp8_veiling_constant", 10.0))
    view_dir = _safe_view_dir(settings)

    rows: List[Dict[str, object]] = []
    worst_obs_id = ""
    worst_value = -1.0
    worst_ti_proxy = -1.0
    worst_ti_percent = -1.0
    worst_row: Dict[str, object] | None = None

    lavg_ref = max(float(lavg_reference_cd_m2), 1e-9)

    for oi, obs in enumerate(observers):
        ox = float(obs.get("x", 0.0))
        oy = float(obs.get("y", 0.0))
        oz = float(obs.get("z", 1.5))
        contribs: List[Dict[str, float]] = []
        total_lv = 0.0

        for li, lum in enumerate(luminaires):
            lx = float(lum.transform.position.x)
            ly = float(lum.transform.position.y)
            lz = float(lum.transform.position.z)

            to_lum = (lx - ox, ly - oy, lz - oz)
            d2 = to_lum[0] * to_lum[0] + to_lum[1] * to_lum[1] + to_lum[2] * to_lum[2]
            if d2 <= 1e-12:
                continue
            d = math.sqrt(d2)

            dot_fwd = (to_lum[0] / d) * view_dir[0] + (to_lum[1] / d) * view_dir[1] + (to_lum[2] / d) * view_dir[2]
            if dot_fwd <= 0.0:
                continue

            theta = math.degrees(math.acos(max(-1.0, min(1.0, dot_fwd))))
            theta = max(theta_min_deg, min(theta_max_deg, theta))

            direction_world = Vector3((ox - lx) / d, (oy - ly) / d, (oz - lz) / d)
            i_cd = float(sample_intensity_cd_world(lum.photometry, lum.transform, direction_world, tilt_deg=lum.tilt_deg))
            i_cd *= float(getattr(lum, "flux_multiplier", 1.0) or 1.0)
            if not math.isfinite(i_cd) or i_cd <= 0.0:
                continue

            e_eye = i_cd / d2
            lv_i = rp8_k * e_eye / max(theta * theta, 1e-9)
            if not math.isfinite(lv_i) or lv_i <= 0.0:
                continue
            total_lv += lv_i
            contribs.append(
                {
                    "luminaire_index": float(li),
                    "distance_m": float(d),
                    "theta_deg": float(theta),
                    "intensity_cd": float(i_cd),
                    "eye_illuminance_lux": float(e_eye),
                    "veiling_luminance_cd_m2": float(lv_i),
                }
            )

        contribs.sort(
            key=lambda c: (
                float(c["luminaire_index"]),
                float(c["theta_deg"]),
                float(c["distance_m"]),
                float(c["intensity_cd"]),
            )
        )
        ratio = total_lv / lavg_ref
        ti_proxy = 100.0 * ratio
        ti_percent = 65.0 * total_lv / max(lavg_ref ** 0.8, 1e-9)
        metric_value = ratio if method == "rp8_veiling_ratio" else ti_percent

        row = {
            "observer_index": float(oi),
            "observer_id": str(obs.get("observer_id", f"obs_{oi+1}")),
            "lane_number": float(obs.get("lane_number", 0.0)),
            "method": method,
            "x": ox,
            "y": oy,
            "z": oz,
            "lavg_reference_cd_m2": float(lavg_ref),
            "veiling_luminance_total_cd_m2": float(total_lv),
            "rp8_veiling_ratio": float(ratio),
            "ti_proxy_percent": float(ti_proxy),
            "ti_percent": float(ti_percent),
            "metric_value": float(metric_value),
            "contributions": contribs,
        }
        rows.append(row)

        obs_id = str(row.get("observer_id", ""))
        if (metric_value > worst_value) or (abs(metric_value - worst_value) <= 1e-12 and obs_id < worst_obs_id):
            worst_value = metric_value
            worst_ti_proxy = ti_proxy
            worst_ti_percent = ti_percent
            worst_obs_id = obs_id
            worst_row = row

    rows.sort(key=lambda r: (int(r.get("observer_index", 0.0)), str(r.get("observer_id", ""))))
    if worst_row is None:
        worst = {
            "method": method,
            "observer_index": -1.0,
            "observer_id": "",
            "metric_value": 0.0,
            "rp8_veiling_ratio_worst": 0.0,
            "ti_proxy_percent_worst": 0.0,
            "ti_percent_worst": 0.0,
            "veiling_luminance_total_worst_cd_m2": 0.0,
        }
    else:
        wr = worst_row
        worst = {
            "method": method,
            "observer_index": float(wr.get("observer_index", 0.0)),
            "observer_id": str(wr.get("observer_id", "")),
            "metric_value": float(wr.get("metric_value", 0.0)),
            "rp8_veiling_ratio_worst": float(wr.get("rp8_veiling_ratio", 0.0)),
            "ti_proxy_percent_worst": float(worst_ti_proxy),
            "ti_percent_worst": float(worst_ti_percent),
            "veiling_luminance_total_worst_cd_m2": float(wr.get("veiling_luminance_total_cd_m2", 0.0)),
        }
    return rows, worst
