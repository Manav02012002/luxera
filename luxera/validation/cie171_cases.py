from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass(frozen=True)
class CIE171Luminaire:
    x: float
    y: float
    z: float
    flux_lumens: float
    distribution: str  # isotropic | cosine | uniform_downward


@dataclass(frozen=True)
class CIE171Case:
    id: str
    description: str
    room_width: float
    room_length: float
    room_height: float
    floor_reflectance: float
    wall_reflectance: float
    ceiling_reflectance: float
    luminaires: List[CIE171Luminaire]
    grid_height: float
    grid_nx: int
    grid_ny: int
    include_interreflections: bool
    reference_E_avg: float
    reference_E_min: float
    reference_E_max: float
    tolerance_pct: float


def _grid_xy(case: CIE171Case) -> tuple[np.ndarray, np.ndarray]:
    xs = np.linspace(0.0, float(case.room_width), int(case.grid_nx), dtype=float)
    ys = np.linspace(0.0, float(case.room_length), int(case.grid_ny), dtype=float)
    return np.meshgrid(xs, ys)


def _analytical_isotropic_grid(case: CIE171Case) -> np.ndarray:
    X, Y = _grid_xy(case)
    Z = np.zeros_like(X, dtype=float)
    for lum in case.luminaires:
        h = float(lum.z - case.grid_height)
        if h <= 1e-12:
            continue
        dx = X - float(lum.x)
        dy = Y - float(lum.y)
        d2 = dx * dx + dy * dy + h * h
        d = np.sqrt(d2)
        I = float(lum.flux_lumens) / (4.0 * np.pi)
        Z += I * (h / d) / d2
    return Z


def _analytical_luminaire_contribution(case: CIE171Case, lum: CIE171Luminaire, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    h = float(lum.z - case.grid_height)
    if h <= 1e-12:
        return np.zeros_like(X, dtype=float)
    dx = X - float(lum.x)
    dy = Y - float(lum.y)
    d2 = dx * dx + dy * dy + h * h
    d = np.sqrt(d2)
    cos_gamma = h / d
    dist = str(lum.distribution).lower()
    if dist == "isotropic":
        I = float(lum.flux_lumens) / (4.0 * np.pi)
        return I * cos_gamma / d2
    if dist == "uniform_downward":
        I = float(lum.flux_lumens) / (2.0 * np.pi)
        return I * cos_gamma / d2
    if dist == "cosine":
        I0 = float(lum.flux_lumens) / np.pi
        return I0 * (h * h) / (d2 * d2)
    raise ValueError(f"Unsupported analytical distribution: {lum.distribution}")


def compute_analytical_reference(case: CIE171Case) -> Tuple[float, float, float]:
    X, Y = _grid_xy(case)
    E = np.zeros_like(X, dtype=float)
    for lum in case.luminaires:
        E += _analytical_luminaire_contribution(case, lum, X, Y)
    return float(np.mean(E)), float(np.min(E)), float(np.max(E))


def compute_high_fidelity_reference(case: CIE171Case) -> Tuple[float, float, float]:
    from luxera.validation.cie171_runner import run_case_high_fidelity_radiosity

    return run_case_high_fidelity_radiosity(
        case,
        engine_config={"max_iters": 500, "tol": 1e-5, "patch_max_area": 0.1, "hemicube_resolution": 256},
    )


def _case_3_luminaires() -> List[CIE171Luminaire]:
    xs = np.linspace(8.0 / 6.0, 8.0 - 8.0 / 6.0, 3, dtype=float)
    ys = np.linspace(6.0 / 4.0, 6.0 - 6.0 / 4.0, 2, dtype=float)
    out: List[CIE171Luminaire] = []
    for y in ys:
        for x in xs:
            out.append(CIE171Luminaire(x=float(x), y=float(y), z=3.0, flux_lumens=5000.0, distribution="cosine"))
    return out


def _case_6_luminaires() -> List[CIE171Luminaire]:
    xs = np.linspace(1.0, 11.0, 6, dtype=float)
    return [CIE171Luminaire(x=float(x), y=1.0, z=3.0, flux_lumens=3000.0, distribution="cosine") for x in xs]


def _case_7_luminaires() -> List[CIE171Luminaire]:
    xs = np.linspace(2.0, 18.0, 5, dtype=float)
    ys = np.linspace(1.5, 13.5, 4, dtype=float)
    out: List[CIE171Luminaire] = []
    for y in ys:
        for x in xs:
            out.append(CIE171Luminaire(x=float(x), y=float(y), z=3.5, flux_lumens=5000.0, distribution="cosine"))
    return out


def _with_analytical_reference(case: CIE171Case) -> CIE171Case:
    avg, mn, mx = compute_analytical_reference(case)
    return CIE171Case(
        **{**case.__dict__, "reference_E_avg": avg, "reference_E_min": mn, "reference_E_max": mx},
    )


_CASES_BASE: List[CIE171Case] = [
    CIE171Case(
        id="case1",
        description="Single isotropic point, absorbing room",
        room_width=4.0,
        room_length=4.0,
        room_height=3.0,
        floor_reflectance=0.0,
        wall_reflectance=0.0,
        ceiling_reflectance=0.0,
        luminaires=[CIE171Luminaire(x=2.0, y=2.0, z=3.0, flux_lumens=1000.0, distribution="isotropic")],
        grid_height=0.85,
        grid_nx=20,
        grid_ny=20,
        include_interreflections=False,
        reference_E_avg=0.0,
        reference_E_min=0.0,
        reference_E_max=0.0,
        tolerance_pct=0.5,
    ),
    CIE171Case(
        id="case2",
        description="Single cosine source, absorbing room",
        room_width=4.0,
        room_length=4.0,
        room_height=3.0,
        floor_reflectance=0.0,
        wall_reflectance=0.0,
        ceiling_reflectance=0.0,
        luminaires=[CIE171Luminaire(x=2.0, y=2.0, z=3.0, flux_lumens=1000.0, distribution="cosine")],
        grid_height=0.85,
        grid_nx=20,
        grid_ny=20,
        include_interreflections=False,
        reference_E_avg=0.0,
        reference_E_min=0.0,
        reference_E_max=0.0,
        tolerance_pct=0.5,
    ),
    CIE171Case(
        id="case3",
        description="2x3 grid of cosine sources, absorbing room",
        room_width=8.0,
        room_length=6.0,
        room_height=3.0,
        floor_reflectance=0.0,
        wall_reflectance=0.0,
        ceiling_reflectance=0.0,
        luminaires=_case_3_luminaires(),
        grid_height=0.85,
        grid_nx=40,
        grid_ny=30,
        include_interreflections=False,
        reference_E_avg=0.0,
        reference_E_min=0.0,
        reference_E_max=0.0,
        tolerance_pct=0.5,
    ),
    CIE171Case(
        id="case4",
        description="Single cosine source, reflecting room",
        room_width=4.0,
        room_length=4.0,
        room_height=3.0,
        floor_reflectance=0.2,
        wall_reflectance=0.5,
        ceiling_reflectance=0.7,
        luminaires=[CIE171Luminaire(x=2.0, y=2.0, z=3.0, flux_lumens=1000.0, distribution="cosine")],
        grid_height=0.85,
        grid_nx=20,
        grid_ny=20,
        include_interreflections=True,
        reference_E_avg=-1.0,
        reference_E_min=-1.0,
        reference_E_max=-1.0,
        tolerance_pct=3.0,
    ),
    CIE171Case(
        id="case5",
        description="High-reflectance room (stress test)",
        room_width=4.0,
        room_length=4.0,
        room_height=3.0,
        floor_reflectance=0.85,
        wall_reflectance=0.85,
        ceiling_reflectance=0.85,
        luminaires=[CIE171Luminaire(x=2.0, y=2.0, z=3.0, flux_lumens=1000.0, distribution="cosine")],
        grid_height=0.85,
        grid_nx=20,
        grid_ny=20,
        include_interreflections=True,
        reference_E_avg=-1.0,
        reference_E_min=-1.0,
        reference_E_max=-1.0,
        tolerance_pct=5.0,
    ),
    CIE171Case(
        id="case6",
        description="Corridor geometry",
        room_width=12.0,
        room_length=2.0,
        room_height=3.0,
        floor_reflectance=0.2,
        wall_reflectance=0.5,
        ceiling_reflectance=0.7,
        luminaires=_case_6_luminaires(),
        grid_height=0.85,
        grid_nx=60,
        grid_ny=10,
        include_interreflections=False,
        reference_E_avg=0.0,
        reference_E_min=0.0,
        reference_E_max=0.0,
        tolerance_pct=0.5,
    ),
    CIE171Case(
        id="case7",
        description="Large room at scale",
        room_width=20.0,
        room_length=15.0,
        room_height=3.5,
        floor_reflectance=0.3,
        wall_reflectance=0.5,
        ceiling_reflectance=0.7,
        luminaires=_case_7_luminaires(),
        grid_height=0.85,
        grid_nx=80,
        grid_ny=60,
        include_interreflections=False,
        reference_E_avg=0.0,
        reference_E_min=0.0,
        reference_E_max=0.0,
        tolerance_pct=0.5,
    ),
    CIE171Case(
        id="case8",
        description="Near-field test",
        room_width=4.0,
        room_length=4.0,
        room_height=2.5,
        floor_reflectance=0.0,
        wall_reflectance=0.0,
        ceiling_reflectance=0.0,
        luminaires=[CIE171Luminaire(x=2.0, y=2.0, z=2.5, flux_lumens=1000.0, distribution="cosine")],
        grid_height=2.0,
        grid_nx=20,
        grid_ny=20,
        include_interreflections=False,
        reference_E_avg=0.0,
        reference_E_min=0.0,
        reference_E_max=0.0,
        tolerance_pct=1.0,
    ),
]

CIE171_CASES: List[CIE171Case] = [
    _with_analytical_reference(c) if not c.include_interreflections else c
    for c in _CASES_BASE
]

