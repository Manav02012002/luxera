from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from luxera.calculation.illuminance import CalculationGrid, Luminaire, calculate_grid_illuminance
from luxera.geometry.core import Vector3, Transform
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt, Photometry
from luxera.project.schema import Project, PhotometryAsset, LuminaireInstance, TransformSpec, RotationSpec


@dataclass(frozen=True)
class LayoutCandidate:
    rows: int
    cols: int
    mean_lux: float
    uniformity: float


def _load_photometry(asset: PhotometryAsset) -> Photometry:
    if asset.path is None:
        raise ValueError("Photometry asset path required for optimization")
    text = open(asset.path, "r", encoding="utf-8", errors="replace").read()
    if asset.format == "IES":
        return photometry_from_parsed_ies(parse_ies_text(text))
    if asset.format == "LDT":
        return photometry_from_parsed_ldt(parse_ldt_text(text))
    raise ValueError(f"Unsupported photometry format: {asset.format}")


def _layout_luminaires(room_w: float, room_l: float, height: float, rows: int, cols: int, phot: Photometry) -> List[Luminaire]:
    luminaires: List[Luminaire] = []
    margin_x = room_w * 0.1
    margin_y = room_l * 0.1
    usable_w = max(0.1, room_w - 2 * margin_x)
    usable_l = max(0.1, room_l - 2 * margin_y)

    dx = usable_w / max(cols, 1)
    dy = usable_l / max(rows, 1)
    start_x = margin_x + dx / 2
    start_y = margin_y + dy / 2

    for r in range(rows):
        for c in range(cols):
            x = start_x + c * dx
            y = start_y + r * dy
            z = height
            lum = Luminaire(photometry=phot, transform=Transform(position=Vector3(x, y, z)))
            luminaires.append(lum)
    return luminaires


def propose_layout(project: Project, target_lux: float, max_rows: int = 6, max_cols: int = 6) -> Tuple[List[LuminaireInstance], LayoutCandidate]:
    if not project.geometry.rooms:
        raise ValueError("Project has no rooms")
    if not project.photometry_assets:
        raise ValueError("Project has no photometry assets")

    room = project.geometry.rooms[0]
    asset = project.photometry_assets[0]
    phot = _load_photometry(asset)

    grid = CalculationGrid(
        origin=Vector3(0, 0, 0),
        width=room.width,
        height=room.length,
        elevation=0.8,
        nx=10,
        ny=10,
    )

    best: Optional[LayoutCandidate] = None
    best_layout: List[LuminaireInstance] = []

    for rows in range(1, max_rows + 1):
        for cols in range(1, max_cols + 1):
            lums = _layout_luminaires(room.width, room.length, room.height * 0.9, rows, cols, phot)
            result = calculate_grid_illuminance(grid, lums)
            cand = LayoutCandidate(rows=rows, cols=cols, mean_lux=result.mean_lux, uniformity=result.uniformity_ratio)
            score = abs(cand.mean_lux - target_lux) + (1.0 - cand.uniformity) * 100.0
            if best is None or score < (abs(best.mean_lux - target_lux) + (1.0 - best.uniformity) * 100.0):
                best = cand
                best_layout = []
                for lum in lums:
                    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
                    inst = LuminaireInstance(
                        id="",
                        name="Luminaire",
                        photometry_asset_id=asset.id,
                        transform=TransformSpec(position=(lum.transform.position.x, lum.transform.position.y, lum.transform.position.z), rotation=rot),
                    )
                    best_layout.append(inst)

    if best is None:
        raise ValueError("Failed to generate layout")

    return best_layout, best
