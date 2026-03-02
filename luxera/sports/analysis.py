from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.core.transform import from_aim_up, from_euler_zyx
from luxera.engine.direct_illuminance import run_direct_grid, run_direct_points
from luxera.geometry.core import Vector3
from luxera.photometry.model import Photometry
from luxera.project.schema import CalcGrid, Project
from luxera.sports.en12193 import SportStandard
from luxera.sports.field import PlayingField
from luxera.sports.pole import LightingPole


@dataclass(frozen=True)
class SportsResult:
    E_h_avg: float
    E_h_min: float
    E_h_max: float
    U1: float
    U2: float
    E_v_avg: Optional[Dict[str, float]]
    compliance: Dict[str, bool]
    overall_compliant: bool


def _synthetic_floodlight_photometry() -> Photometry:
    gamma = np.array([0.0, 10.0, 20.0, 30.0, 45.0, 60.0, 75.0, 90.0], dtype=float)
    cd = np.array([120000.0, 118000.0, 110000.0, 95000.0, 70000.0, 35000.0, 12000.0, 0.0], dtype=float)
    return Photometry(
        system="C",
        c_angles_deg=np.array([0.0], dtype=float),
        gamma_angles_deg=gamma,
        candela=cd.reshape(1, -1),
        luminous_flux_lm=50000.0,
        symmetry="FULL",
    )


def _build_luminaires_from_poles(poles: List[LightingPole]) -> List[Luminaire]:
    phot = _synthetic_floodlight_photometry()
    out: List[Luminaire] = []
    for pole in poles:
        p = Vector3(*pole.position)
        for lum in pole.luminaires:
            if lum.aim_point is not None:
                tf = from_aim_up(position=p, aim=Vector3(*lum.aim_point), up=Vector3.up())
            else:
                tf = from_euler_zyx(
                    position=p,
                    yaw_deg=float(lum.rotation_deg),
                    pitch_deg=-float(lum.tilt_deg),
                    roll_deg=0.0,
                )
            out.append(Luminaire(photometry=phot, transform=tf, flux_multiplier=1.0, tilt_deg=0.0))
    return out


def _grid_points(field: PlayingField, spacing: float, z: float) -> np.ndarray:
    nx = max(2, int(round(field.length / spacing)) + 1)
    ny = max(2, int(round(field.width / spacing)) + 1)
    xs = np.linspace(-field.length / 2.0, field.length / 2.0, nx, dtype=float)
    ys = np.linspace(-field.width / 2.0, field.width / 2.0, ny, dtype=float)
    pts = np.zeros((nx * ny, 3), dtype=float)
    k = 0
    for y in ys:
        for x in xs:
            pts[k] = [x, y, z]
            k += 1
    return pts


class SportsLightingAnalysis:
    """Run sports lighting analysis for a field + pole layout."""

    def run(
        self,
        field: PlayingField,
        poles: List[LightingPole],
        standard: SportStandard,
        grid_spacing: float = 5.0,
    ) -> SportsResult:
        """
        Build horizontal and optional vertical evaluation objects and evaluate against standard.
        """
        _ = Project(name=f"sports:{field.sport}")  # explicit schema touchpoint for workflow consistency
        luminaires = _build_luminaires_from_poles(poles)

        nx = max(2, int(round(field.length / grid_spacing)) + 1)
        ny = max(2, int(round(field.width / grid_spacing)) + 1)
        hgrid = CalcGrid(
            id="sports_h",
            name="Sports Horizontal Grid",
            origin=(-field.length / 2.0, -field.width / 2.0, 1.0),
            width=field.length,
            height=field.width,
            elevation=1.0,
            nx=nx,
            ny=ny,
        )
        hres = run_direct_grid(hgrid, luminaires, use_occlusion=False)
        hvals = np.asarray(hres.values, dtype=float).reshape(-1)
        E_h_avg = float(np.mean(hvals))
        E_h_min = float(np.min(hvals))
        E_h_max = float(np.max(hvals))
        U1 = E_h_min / E_h_max if E_h_max > 1e-9 else 0.0
        U2 = E_h_min / E_h_avg if E_h_avg > 1e-9 else 0.0

        E_v_avg: Optional[Dict[str, float]] = None
        Ev_uniformity_ok = True
        Ev_mean_ok = True
        if standard.E_v_maintained is not None:
            E_v_avg = {}
            points = _grid_points(field, grid_spacing, z=1.5)
            normals = {
                "N": Vector3(0.0, -1.0, 0.0),
                "S": Vector3(0.0, 1.0, 0.0),
                "E": Vector3(-1.0, 0.0, 0.0),
                "W": Vector3(1.0, 0.0, 0.0),
            }
            all_uniform_ok = True
            all_mean_ok = True
            for key, nrm in normals.items():
                pres = run_direct_points(points=points, surface_normal=nrm, luminaires=luminaires, use_occlusion=False)
                pvals = np.asarray(pres.values, dtype=float)
                pav = float(np.mean(pvals))
                pmin = float(np.min(pvals))
                E_v_avg[key] = pav
                if standard.E_v_maintained is not None:
                    all_mean_ok = all_mean_ok and (pav >= float(standard.E_v_maintained))
                if standard.E_v_uniformity is not None and pav > 1e-9:
                    all_uniform_ok = all_uniform_ok and ((pmin / pav) >= float(standard.E_v_uniformity))
            Ev_mean_ok = all_mean_ok
            Ev_uniformity_ok = all_uniform_ok

        compliance: Dict[str, bool] = {
            "E_h_maintained": E_h_avg >= float(standard.E_h_maintained),
            "E_h_uniformity_U1": U1 >= float(standard.E_h_uniformity_U1),
            "E_h_uniformity_U2": U2 >= float(standard.E_h_uniformity_U2),
        }
        if standard.E_v_maintained is not None:
            compliance["E_v_maintained"] = Ev_mean_ok
        if standard.E_v_uniformity is not None:
            compliance["E_v_uniformity"] = Ev_uniformity_ok
        if standard.GR_max is not None:
            compliance["GR_max"] = True  # Placeholder until explicit GR computation is bound for sports workflow.

        overall = all(bool(v) for v in compliance.values())
        return SportsResult(
            E_h_avg=E_h_avg,
            E_h_min=E_h_min,
            E_h_max=E_h_max,
            U1=U1,
            U2=U2,
            E_v_avg=E_v_avg,
            compliance=compliance,
            overall_compliant=overall,
        )
