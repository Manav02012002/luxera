from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from luxera.calculation.illuminance import CalculationGrid, DirectCalcSettings, Luminaire, calculate_grid_illuminance
from luxera.geometry.core import Transform, Vector3
from luxera.geometry.spatial import point_in_polygon
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import Photometry, photometry_from_parsed_ies, photometry_from_parsed_ldt
from luxera.project.schema import Project


@dataclass(frozen=True)
class ExteriorAreaSpec:
    """Defines an outdoor calculation area."""

    name: str
    boundary_polygon: List[Tuple[float, float]]
    ground_reflectance: float = 0.1
    grid_height: float = 0.0
    grid_spacing: float = 5.0


@dataclass(frozen=True)
class PoleSpec:
    """Outdoor lighting pole with one or more luminaires."""

    id: str
    position: Tuple[float, float, float]
    luminaire_asset_id: str
    luminaire_count: int = 1
    arm_length_m: float = 2.0
    arm_angles_deg: List[float] = field(default_factory=lambda: [0.0])
    tilt_deg: float = 15.0


class ExteriorAreaEngine:
    """Compute illuminance for outdoor areas."""

    def generate_grid_points(self, area: ExteriorAreaSpec) -> np.ndarray:
        poly = [(float(x), float(y)) for x, y in area.boundary_polygon]
        if len(poly) < 3:
            raise ValueError("Exterior area boundary polygon requires at least 3 vertices")

        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        spacing = max(1e-3, float(area.grid_spacing))

        x0 = min(xs) + 0.5 * spacing
        x1 = max(xs)
        y0 = min(ys) + 0.5 * spacing
        y1 = max(ys)

        points: List[Tuple[float, float, float]] = []
        x = x0
        while x < x1:
            y = y0
            while y < y1:
                if point_in_polygon((x, y), poly):
                    points.append((float(x), float(y), float(area.grid_height)))
                y += spacing
            x += spacing

        return np.asarray(points, dtype=float)

    def create_luminaires_from_poles(self, poles: List[PoleSpec], project: Project) -> List[Luminaire]:
        assets = {a.id: a for a in project.photometry_assets}
        phot_cache: Dict[str, Photometry] = {}
        luminaires: List[Luminaire] = []

        for pole in poles:
            asset = assets.get(pole.luminaire_asset_id)
            if asset is None:
                raise ValueError(f"Missing photometry asset: {pole.luminaire_asset_id}")
            phot = phot_cache.get(asset.id)
            if phot is None:
                phot = self._photometry_from_asset(project, asset.id)
                phot_cache[asset.id] = phot

            count = max(1, int(pole.luminaire_count))
            angles = pole.arm_angles_deg or [0.0]
            for i in range(count):
                arm_deg = float(angles[i % len(angles)])
                arm_rad = math.radians(arm_deg)
                px, py, pz = pole.position
                lx = float(px + pole.arm_length_m * math.cos(arm_rad))
                ly = float(py + pole.arm_length_m * math.sin(arm_rad))
                lz = float(pz)

                yaw = (arm_deg + 180.0) % 360.0
                tf = Transform.from_euler_zyx(Vector3(lx, ly, lz), yaw_deg=yaw, pitch_deg=float(pole.tilt_deg), roll_deg=0.0)
                luminaires.append(
                    Luminaire(
                        photometry=phot,
                        transform=tf,
                        flux_multiplier=1.0,
                        tilt_deg=float(pole.tilt_deg),
                    )
                )

        return luminaires

    def compute(self, area: ExteriorAreaSpec, poles: List[PoleSpec], project: Project) -> Dict[str, Any]:
        points = self.generate_grid_points(area)
        luminaires = self.create_luminaires_from_poles(poles, project)

        if points.size == 0:
            return {
                "area_name": area.name,
                "grid_points": points,
                "grid_values": np.zeros((0, 0), dtype=float),
                "values_flat": np.zeros((0,), dtype=float),
                "E_avg": 0.0,
                "E_min": 0.0,
                "E_max": 0.0,
                "U0": 0.0,
                "grid_spacing": float(area.grid_spacing),
                "grid_height": float(area.grid_height),
            }

        n_points = int(points.shape[0])
        grid = CalculationGrid(
            origin=Vector3(float(points[0, 0]), float(points[0, 1]), float(area.grid_height)),
            width=0.0,
            height=0.0,
            elevation=float(area.grid_height),
            nx=n_points,
            ny=1,
            normal=Vector3(0.0, 0.0, 1.0),
        )

        # Override get_points/get_point so we can use irregular polygon-clipped points.
        grid_points_vec = [Vector3(float(p[0]), float(p[1]), float(p[2])) for p in points]

        def _get_points() -> List[Vector3]:
            return grid_points_vec

        def _get_point(i: int, _j: int) -> Vector3:
            return grid_points_vec[i]

        grid.get_points = _get_points  # type: ignore[assignment]
        grid.get_point = _get_point  # type: ignore[assignment]

        result = calculate_grid_illuminance(
            grid,
            luminaires,
            occluders=None,
            settings=DirectCalcSettings(use_occlusion=False),
        )

        vals = result.values.reshape(-1)
        e_avg = float(np.mean(vals)) if vals.size else 0.0
        e_min = float(np.min(vals)) if vals.size else 0.0
        e_max = float(np.max(vals)) if vals.size else 0.0
        u0 = e_min / e_avg if e_avg > 1e-12 else 0.0

        return {
            "area_name": area.name,
            "grid_points": points,
            "grid_values": result.values,
            "values_flat": vals,
            "E_avg": e_avg,
            "E_min": e_min,
            "E_max": e_max,
            "U0": u0,
            "grid_spacing": float(area.grid_spacing),
            "grid_height": float(area.grid_height),
        }

    def _photometry_from_asset(self, project: Project, asset_id: str) -> Photometry:
        asset = next((a for a in project.photometry_assets if a.id == asset_id), None)
        if asset is None:
            raise ValueError(f"Missing photometry asset: {asset_id}")

        text: str
        source_path: Path | None = None
        if asset.embedded_b64:
            text = base64.b64decode(asset.embedded_b64.encode("utf-8")).decode("utf-8", errors="replace")
        elif asset.path:
            p = Path(asset.path).expanduser()
            if not p.is_absolute() and project.root_dir:
                p = (Path(project.root_dir).expanduser() / p).resolve()
            source_path = p.resolve()
            text = source_path.read_text(encoding="utf-8", errors="replace")
        else:
            raise ValueError(f"Photometry asset {asset_id} has no file path or embedded payload")

        fmt = str(asset.format).upper()
        if fmt == "IES":
            return photometry_from_parsed_ies(parse_ies_text(text, source_path=source_path))
        if fmt == "LDT":
            return photometry_from_parsed_ldt(parse_ldt_text(text))
        raise ValueError(f"Unsupported photometry format: {asset.format}")
