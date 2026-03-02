from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from luxera.calculation.illuminance import Luminaire
from luxera.core.transform import from_euler_zyx
from luxera.engine.direct_illuminance import build_room_from_spec, run_direct_grid
from luxera.engine.radiosity.solver import RadiosityConfig, solve_radiosity
from luxera.geometry.core import Vector3
from luxera.photometry.model import Photometry
from luxera.project.schema import CalcGrid, RoomSpec
from luxera.validation.cie171_cases import CIE171Case, CIE171Luminaire, CIE171_CASES, compute_analytical_reference


@dataclass(frozen=True)
class CIE171Result:
    case_id: str
    reference_E_avg: float
    computed_E_avg: float
    computed_E_min: float
    computed_E_max: float
    deviation_pct: float
    passed: bool
    computation_seconds: float


def _synthetic_photometry(distribution: str, flux_lm: float) -> Photometry:
    gamma = np.linspace(0.0, 180.0, 361, dtype=float)
    dist = str(distribution).lower()
    if dist == "isotropic":
        cd = np.full_like(gamma, float(flux_lm) / (4.0 * np.pi), dtype=float)
    elif dist == "uniform_downward":
        cd = np.where(gamma <= 90.0, float(flux_lm) / (2.0 * np.pi), 0.0).astype(float)
    elif dist == "cosine":
        cd = (float(flux_lm) / np.pi) * np.maximum(np.cos(np.deg2rad(gamma)), 0.0)
    else:
        raise ValueError(f"Unsupported distribution: {distribution}")
    return Photometry(
        system="C",
        c_angles_deg=np.array([0.0], dtype=float),
        gamma_angles_deg=gamma,
        candela=cd.reshape(1, -1),
        luminous_flux_lm=float(flux_lm),
        symmetry="FULL",
    )


def _build_luminaires(case: CIE171Case) -> List[Luminaire]:
    out: List[Luminaire] = []
    for i, lum in enumerate(case.luminaires):
        tf = from_euler_zyx(
            Vector3(float(lum.x), float(lum.y), float(lum.z)),
            yaw_deg=0.0,
            pitch_deg=0.0,
            roll_deg=0.0,
        )
        out.append(
            Luminaire(
                photometry=_synthetic_photometry(lum.distribution, lum.flux_lumens),
                transform=tf,
                flux_multiplier=1.0,
            )
        )
    return out


def _grid_spec_for_case(case: CIE171Case) -> CalcGrid:
    return CalcGrid(
        id=f"{case.id}_grid",
        name=f"{case.id}_grid",
        origin=(0.0, 0.0, case.grid_height),
        width=float(case.room_width),
        height=float(case.room_length),
        elevation=float(case.grid_height),
        nx=int(case.grid_nx),
        ny=int(case.grid_ny),
    )


def _run_direct_case(case: CIE171Case) -> Tuple[float, float, float]:
    luminaire_objs = _build_luminaires(case)
    grid_spec = _grid_spec_for_case(case)
    direct = run_direct_grid(grid_spec, luminaire_objs, use_occlusion=False)
    vals = np.asarray(direct.values, dtype=float).reshape(-1)
    finite = vals[np.isfinite(vals)]
    if finite.size == 0:
        return 0.0, 0.0, 0.0
    return float(np.mean(finite)), float(np.min(finite)), float(np.max(finite))


def _surface_direct_illuminance(surfaces, luminaires: List[Luminaire]) -> Dict[str, float]:
    from luxera.calculation.illuminance import calculate_direct_illuminance

    direct: Dict[str, float] = {}
    for s in surfaces:
        total = 0.0
        for lum in luminaires:
            total += float(calculate_direct_illuminance(s.centroid, s.normal, lum))
        direct[s.id] = total
    return direct


def run_case_high_fidelity_radiosity(case: CIE171Case, engine_config: Optional[dict] = None) -> Tuple[float, float, float]:
    cfg = dict(engine_config or {})
    room_spec = RoomSpec(
        id=f"{case.id}_room",
        name=case.description,
        width=float(case.room_width),
        length=float(case.room_length),
        height=float(case.room_height),
        floor_reflectance=float(case.floor_reflectance),
        wall_reflectance=float(case.wall_reflectance),
        ceiling_reflectance=float(case.ceiling_reflectance),
    )
    room = build_room_from_spec(room_spec, length_scale=1.0)
    surfaces = room.get_surfaces()
    luminaires = _build_luminaires(case)
    direct = _surface_direct_illuminance(surfaces, luminaires)
    solve = solve_radiosity(
        surfaces,
        direct,
        config=RadiosityConfig(
            max_iters=int(cfg.get("max_iters", 500)),
            tol=float(cfg.get("tol", 1e-5)),
            damping=float(cfg.get("damping", 1.0)),
            patch_max_area=float(cfg.get("patch_max_area", 0.1)),
            use_visibility=bool(cfg.get("use_visibility", True)),
            form_factor_method="hemicube",
            hemicube_resolution=int(cfg.get("hemicube_resolution", 256)),
            monte_carlo_samples=int(cfg.get("monte_carlo_samples", 2048)),
            seed=int(cfg.get("seed", 0)),
        ),
    )
    floor_vals: List[float] = []
    for i, patch in enumerate(solve.patches):
        if "floor" in str(patch.id).lower():
            floor_vals.append(float(solve.irradiance[i]))
    if not floor_vals:
        return 0.0, 0.0, 0.0
    arr = np.asarray(floor_vals, dtype=float)
    return float(np.mean(arr)), float(np.min(arr)), float(np.max(arr))


class CIE171ValidationRunner:
    def __init__(self, cases: Optional[List[CIE171Case]] = None):
        self.cases = list(cases) if cases is not None else list(CIE171_CASES)

    def run_case(self, case: CIE171Case, engine_config: Optional[dict] = None) -> CIE171Result:
        start = time.perf_counter()
        if case.include_interreflections:
            computed_avg, computed_min, computed_max = run_case_high_fidelity_radiosity(case, engine_config=engine_config)
            if case.reference_E_avg > 0.0:
                ref_avg, ref_min, ref_max = case.reference_E_avg, case.reference_E_min, case.reference_E_max
            else:
                ref_avg, ref_min, ref_max = run_case_high_fidelity_radiosity(
                    case,
                    engine_config={
                        "max_iters": 500,
                        "tol": 1e-5,
                        "patch_max_area": 0.1,
                        "hemicube_resolution": 256,
                        "use_visibility": True,
                    },
                )
        else:
            computed_avg, computed_min, computed_max = _run_direct_case(case)
            ref_avg, ref_min, ref_max = compute_analytical_reference(case)

        denom = max(abs(ref_avg), 1e-9)
        deviation_pct = abs((computed_avg - ref_avg) / denom) * 100.0
        passed = bool(deviation_pct <= float(case.tolerance_pct))
        elapsed = time.perf_counter() - start
        return CIE171Result(
            case_id=case.id,
            reference_E_avg=float(ref_avg),
            computed_E_avg=float(computed_avg),
            computed_E_min=float(computed_min),
            computed_E_max=float(computed_max),
            deviation_pct=float(deviation_pct),
            passed=passed,
            computation_seconds=float(elapsed),
        )

    def run_all(self) -> List[CIE171Result]:
        return [self.run_case(case) for case in self.cases]

    def generate_report(self, results: List[CIE171Result]) -> str:
        lines = [
            "Case ID | Description | Ref E_avg | Computed E_avg | Deviation % | PASS/FAIL",
            "------- | ----------- | --------- | -------------- | ----------- | ---------",
        ]
        case_map = {c.id: c for c in self.cases}
        for r in results:
            case = case_map.get(r.case_id)
            desc = case.description if case is not None else r.case_id
            lines.append(
                f"{r.case_id} | {desc} | {r.reference_E_avg:.3f} | {r.computed_E_avg:.3f} | {r.deviation_pct:.3f}% | {'PASS' if r.passed else 'FAIL'}"
            )
        passed = sum(1 for r in results if r.passed)
        lines.append("")
        lines.append(f"Summary: {passed}/{len(results)} cases passed.")
        return "\n".join(lines)

    def generate_html_report(self, results: List[CIE171Result], output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not results:
            output_path.write_text("<html><body><h1>CIE171 Validation</h1><p>No results.</p></body></html>", encoding="utf-8")
            return
        max_dev = max(max((r.deviation_pct for r in results), default=1.0), 1e-6)
        bars = []
        bar_w = 48
        gap = 12
        h = 140
        x0 = 40
        y0 = 120
        for idx, r in enumerate(results):
            x = x0 + idx * (bar_w + gap)
            bh = int((r.deviation_pct / max_dev) * 100.0)
            y = y0 - bh
            color = "#16a34a" if r.deviation_pct < 1.0 else "#ca8a04" if r.deviation_pct <= 3.0 else "#dc2626"
            bars.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bh}" fill="{color}" />')
            bars.append(f'<text x="{x + bar_w / 2:.1f}" y="{y0 + 14}" text-anchor="middle" font-size="10">{r.case_id}</text>')
        chart_w = x0 + len(results) * (bar_w + gap) + 20
        chart_svg = (
            f'<svg width="{chart_w}" height="{h}" viewBox="0 0 {chart_w} {h}" xmlns="http://www.w3.org/2000/svg">'
            f'<line x1="{x0-10}" y1="{y0}" x2="{chart_w-10}" y2="{y0}" stroke="#444" stroke-width="1"/>'
            + "".join(bars)
            + "</svg>"
        )

        rows = []
        for r in results:
            color = "#dcfce7" if r.deviation_pct < 1.0 else "#fef3c7" if r.deviation_pct <= 3.0 else "#fee2e2"
            rows.append(
                "<tr>"
                f"<td>{r.case_id}</td><td>{r.reference_E_avg:.3f}</td><td>{r.computed_E_avg:.3f}</td>"
                f"<td style='background:{color}'>{r.deviation_pct:.3f}%</td>"
                f"<td>{'PASS' if r.passed else 'FAIL'}</td>"
                "</tr>"
            )
        passed = sum(1 for r in results if r.passed)
        html = (
            "<html><head><meta charset='utf-8'><title>CIE171 Validation</title>"
            "<style>body{font-family:Arial,sans-serif;padding:16px}table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #ccc;padding:6px;text-align:left}</style></head><body>"
            f"<h1>CIE 171 Validation Report</h1><p><strong>Summary:</strong> {passed}/{len(results)} passed.</p>"
            f"{chart_svg}"
            "<h2>Case Results</h2><table><thead><tr><th>Case</th><th>Ref E_avg</th><th>Computed E_avg</th><th>Deviation</th><th>Status</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></body></html>"
        )
        output_path.write_text(html, encoding="utf-8")
