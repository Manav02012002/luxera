from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from luxera.calculation.illuminance import (
    CalculationGrid,
    DirectCalcSettings,
    IlluminanceResult,
    Luminaire,
    calculate_grid_illuminance,
)
from luxera.geometry.core import Material, Polygon, Room, Surface, Vector3
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.photometry.model import photometry_from_parsed_ies, photometry_from_parsed_ldt
from luxera.project.schema import CalcGrid, Project, RoomSpec


@dataclass(frozen=True)
class DirectGridResult:
    points: np.ndarray
    values: np.ndarray
    nx: int
    ny: int
    result: IlluminanceResult


def build_grid_from_spec(grid_spec: CalcGrid) -> CalculationGrid:
    return CalculationGrid(
        origin=Vector3(*grid_spec.origin),
        width=grid_spec.width,
        height=grid_spec.height,
        elevation=grid_spec.elevation,
        nx=grid_spec.nx,
        ny=grid_spec.ny,
        normal=Vector3(*grid_spec.normal),
    )


def build_room_from_spec(spec: RoomSpec) -> Room:
    floor_mat = Material(name="floor", reflectance=spec.floor_reflectance)
    wall_mat = Material(name="wall", reflectance=spec.wall_reflectance)
    ceiling_mat = Material(name="ceiling", reflectance=spec.ceiling_reflectance)
    origin = Vector3(*spec.origin)
    return Room.rectangular(
        name=spec.name,
        width=spec.width,
        length=spec.length,
        height=spec.height,
        origin=origin,
        floor_material=floor_mat,
        wall_material=wall_mat,
        ceiling_material=ceiling_mat,
    )


def load_luminaires(project: Project, hash_asset_fn) -> tuple[List[Luminaire], Dict[str, str]]:
    assets_by_id = {a.id: a for a in project.photometry_assets}
    luminaires: List[Luminaire] = []
    asset_hashes: Dict[str, str] = {}
    for inst in project.luminaires:
        asset = assets_by_id.get(inst.photometry_asset_id)
        if asset is None:
            raise ValueError(f"Missing photometry asset: {inst.photometry_asset_id}")
        if asset.embedded_b64:
            import base64

            text = base64.b64decode(asset.embedded_b64.encode("utf-8")).decode("utf-8", errors="replace")
        elif asset.path:
            text = open(asset.path, "r", encoding="utf-8", errors="replace").read()
        else:
            raise ValueError(f"Photometry asset {asset.id} has no data")
        if asset.format == "IES":
            phot = photometry_from_parsed_ies(parse_ies_text(text))
        elif asset.format == "LDT":
            phot = photometry_from_parsed_ldt(parse_ldt_text(text))
        else:
            raise ValueError(f"Unsupported photometry format: {asset.format}")

        luminaires.append(
            Luminaire(
                photometry=phot,
                transform=inst.transform.to_transform(),
                flux_multiplier=inst.flux_multiplier,
                tilt_deg=inst.tilt_deg,
            )
        )
        asset_hashes[asset.id] = asset.content_hash or hash_asset_fn(asset)
    return luminaires, asset_hashes


def build_direct_occluders(project: Project, include_room_shell: bool = False) -> List[Surface]:
    surfaces: List[Surface] = []
    material_by_id = {m.id: m for m in project.materials}

    for s in project.geometry.surfaces:
        if len(s.vertices) < 3:
            continue
        verts = [Vector3(*v) for v in s.vertices]
        polygon = Polygon(verts)
        m_spec = material_by_id.get(s.material_id) if s.material_id else None
        material = Material(
            name=f"occluder:{s.id}",
            reflectance=(m_spec.reflectance if m_spec is not None else 0.5),
            specularity=(m_spec.specularity if m_spec is not None else 0.0),
        )
        surfaces.append(Surface(id=s.id, polygon=polygon, material=material))

    if include_room_shell and project.geometry.rooms:
        room = build_room_from_spec(project.geometry.rooms[0])
        surfaces.extend(room.get_surfaces())

    return surfaces


def run_direct_grid(
    grid_spec: CalcGrid,
    luminaires: List[Luminaire],
    occluders: Optional[List[Surface]] = None,
    use_occlusion: bool = False,
    occlusion_epsilon: float = 1e-6,
) -> DirectGridResult:
    grid = build_grid_from_spec(grid_spec)
    settings = DirectCalcSettings(use_occlusion=use_occlusion, occlusion_epsilon=occlusion_epsilon)
    result = calculate_grid_illuminance(grid, luminaires, occluders=occluders, settings=settings)
    points = np.array([p.to_tuple() for p in grid.get_points()], dtype=float)
    return DirectGridResult(
        points=points,
        values=result.values.reshape(-1),
        nx=grid.nx,
        ny=grid.ny,
        result=result,
    )
