from __future__ import annotations
"""Contract: docs/spec/roadway_luminance_model.md."""

import csv
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np

from luxera.calculation.illuminance import Luminaire, calculate_direct_illuminance
from luxera.geometry.core import Vector3


@dataclass(frozen=True)
class SurfaceReflectionTable:
    surface_class: str
    beta_deg: np.ndarray
    tan_gamma: np.ndarray
    values: np.ndarray


@dataclass(frozen=True)
class ReflectionLookupResult:
    value: float
    beta_deg: float
    tan_gamma: float
    clamped: bool


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "road_surfaces"


@lru_cache(maxsize=1)
def load_surface_presets() -> Dict[str, SurfaceReflectionTable]:
    root = _data_dir()
    payload = json.loads((root / "presets.json").read_text(encoding="utf-8"))
    out: Dict[str, SurfaceReflectionTable] = {}
    for row in sorted(payload.get("surfaces", []), key=lambda r: str(r.get("id", ""))):
        sid = str(row["id"]).upper()
        tpath = root / str(row["table"])
        out[sid] = _load_surface_table(sid, tpath)
    return out


@lru_cache(maxsize=16)
def _load_surface_table(surface_class: str, path: Path) -> SurfaceReflectionTable:
    with path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.reader(f)
        rows = list(rdr)
    if not rows:
        raise ValueError(f"Empty road reflection table: {path}")

    header = [str(x).strip() for x in rows[0]]
    if len(header) < 2 or header[0] != "beta_deg":
        raise ValueError(f"Invalid road reflection table header: {path}")

    tan_gamma: List[float] = []
    for col in header[1:]:
        if not col.startswith("tan_gamma_"):
            raise ValueError(f"Invalid tan-gamma header '{col}' in {path}")
        tan_gamma.append(float(col.split("tan_gamma_", 1)[1]))

    beta_rows: List[float] = []
    vals_rows: List[List[float]] = []
    for r in rows[1:]:
        if not r:
            continue
        beta_rows.append(float(r[0]))
        vals_rows.append([float(x) for x in r[1 : 1 + len(tan_gamma)]])

    beta_arr = np.asarray(beta_rows, dtype=np.float64)
    tan_arr = np.asarray(tan_gamma, dtype=np.float64)
    vals = np.asarray(vals_rows, dtype=np.float64)
    if vals.shape != (beta_arr.size, tan_arr.size):
        raise ValueError(f"Table shape mismatch in {path}: {vals.shape}")

    return SurfaceReflectionTable(surface_class=surface_class, beta_deg=beta_arr, tan_gamma=tan_arr, values=vals)


def resolve_surface_class(settings: Dict[str, object]) -> str:
    presets = load_surface_presets()
    requested = str(settings.get("road_surface_class", "R3")).upper()
    if requested in presets:
        return requested
    if "R3" in presets:
        return "R3"
    return sorted(presets.keys())[0]


def _bracket(arr: np.ndarray, value: float) -> Tuple[int, int, float]:
    if arr.size == 1:
        return 0, 0, 0.0
    if value <= float(arr[0]):
        return 0, 0, 0.0
    if value >= float(arr[-1]):
        hi = int(arr.size - 1)
        return hi, hi, 0.0
    hi = int(np.searchsorted(arr, value, side="right"))
    lo = max(0, hi - 1)
    a = float(arr[lo])
    b = float(arr[hi])
    t = (value - a) / max(b - a, 1e-12)
    return lo, hi, float(np.clip(t, 0.0, 1.0))


def lookup_reflection_coefficient(surface_class: str, beta_deg: float, tan_gamma: float) -> ReflectionLookupResult:
    table = load_surface_presets()[surface_class.upper()]
    beta_in = float(beta_deg)
    tan_in = float(tan_gamma)

    beta_c = float(np.clip(beta_in, float(table.beta_deg[0]), float(table.beta_deg[-1])))
    tan_c = float(np.clip(tan_in, float(table.tan_gamma[0]), float(table.tan_gamma[-1])))
    clamped = bool((beta_c != beta_in) or (tan_c != tan_in))

    b0, b1, bt = _bracket(table.beta_deg, beta_c)
    t0, t1, tt = _bracket(table.tan_gamma, tan_c)

    v00 = float(table.values[b0, t0])
    v01 = float(table.values[b0, t1])
    v10 = float(table.values[b1, t0])
    v11 = float(table.values[b1, t1])

    v0 = v00 * (1.0 - tt) + v01 * tt
    v1 = v10 * (1.0 - tt) + v11 * tt
    v = v0 * (1.0 - bt) + v1 * bt
    if not math.isfinite(v):
        v = 0.0
    return ReflectionLookupResult(value=float(v), beta_deg=beta_c, tan_gamma=tan_c, clamped=clamped)


def _safe_unit_xy(vec: np.ndarray) -> np.ndarray:
    h = np.asarray([vec[0], vec[1]], dtype=np.float64)
    n = float(np.linalg.norm(h))
    if n <= 1e-12:
        return np.asarray([1.0, 0.0], dtype=np.float64)
    return h / n


def _compute_beta_deg(light_vec: np.ndarray, view_vec: np.ndarray) -> float:
    lh = _safe_unit_xy(light_vec)
    vh = _safe_unit_xy(view_vec)
    d = float(np.clip(np.dot(lh, vh), -1.0, 1.0))
    beta = float(np.degrees(np.arccos(d)))
    # Road reflection tables are typically symmetric in azimuth.
    return float(min(beta, 180.0 - beta))


def _compute_tan_gamma(view_vec: np.ndarray) -> float:
    hz = float(np.linalg.norm(view_vec[:2]))
    vz = abs(float(view_vec[2]))
    if hz <= 1e-12:
        return 5.0
    return float(vz / hz)


def compute_observer_point_luminance(
    points_xyz: np.ndarray,
    observers: Sequence[Dict[str, float | str]],
    luminaires: Sequence[Luminaire],
    *,
    surface_class: str,
) -> tuple[np.ndarray, Dict[str, float]]:
    pts = np.asarray(points_xyz, dtype=np.float64).reshape(-1, 3)
    obs_rows = list(observers)
    out = np.zeros((len(obs_rows), pts.shape[0]), dtype=np.float64)

    clamp_count = 0
    nan_guard_count = 0
    n = Vector3(0.0, 0.0, 1.0)

    for oi, obs in enumerate(obs_rows):
        ox = float(obs.get("x", 0.0))
        oy = float(obs.get("y", 0.0))
        oz = float(obs.get("z", 1.5))
        observer = np.asarray([ox, oy, oz], dtype=np.float64)

        for pi, p in enumerate(pts):
            pvec = Vector3(float(p[0]), float(p[1]), float(p[2]))
            view_vec = observer - p
            p_lum = 0.0

            for lum in luminaires:
                light_vec = np.asarray(
                    [
                        float(lum.transform.position.x - p[0]),
                        float(lum.transform.position.y - p[1]),
                        float(lum.transform.position.z - p[2]),
                    ],
                    dtype=np.float64,
                )
                dist = float(np.linalg.norm(light_vec))
                if dist <= 1e-9:
                    continue

                cos_inc = float(light_vec[2] / dist)
                cos_inc = float(np.clip(cos_inc, 0.0, 1.0))
                if cos_inc <= 0.0:
                    continue

                e_i = float(calculate_direct_illuminance(pvec, n, lum))
                if not math.isfinite(e_i) or e_i <= 0.0:
                    continue

                beta = _compute_beta_deg(light_vec, view_vec)
                tan_gamma = _compute_tan_gamma(view_vec)
                looked = lookup_reflection_coefficient(surface_class, beta, tan_gamma)
                if looked.clamped:
                    clamp_count += 1
                rcoef = float(looked.value)
                if not math.isfinite(rcoef):
                    nan_guard_count += 1
                    rcoef = 0.0

                # Simplified reduced luminance coefficient model: L = E_i * r(beta, tan(gamma)).
                contrib = e_i * rcoef
                if not math.isfinite(contrib):
                    nan_guard_count += 1
                    contrib = 0.0
                p_lum += contrib

            out[oi, pi] = p_lum

    out = np.nan_to_num(out, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    return out, {
        "surface_class": surface_class,
        "clamp_count": float(clamp_count),
        "nan_guard_count": float(nan_guard_count),
    }
