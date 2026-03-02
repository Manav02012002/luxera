from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from luxera.sports.field import PlayingField


@dataclass
class PoleLuminaire:
    photometry_asset_id: str
    tilt_deg: float
    rotation_deg: float
    aim_point: Optional[Tuple[float, float, float]] = None


@dataclass
class LightingPole:
    id: str
    position: Tuple[float, float, float]
    luminaires: List[PoleLuminaire] = field(default_factory=list)


class PoleLayout:
    """Generate standard pole arrangements for sports fields."""

    @staticmethod
    def _field_corners(field: PlayingField, pole_height: float, offset: float) -> list[Tuple[float, float, float]]:
        hx = field.total_length / 2.0 + float(offset)
        hy = field.total_width / 2.0 + float(offset)
        return [
            (-hx, -hy, pole_height),
            (-hx, hy, pole_height),
            (hx, -hy, pole_height),
            (hx, hy, pole_height),
        ]

    @staticmethod
    def _default_luminaire_at(pole: LightingPole, aim_point: Tuple[float, float, float]) -> PoleLuminaire:
        tilt, rot = PoleLayout.compute_aiming(pole, aim_point)
        return PoleLuminaire(
            photometry_asset_id="default_floodlight",
            tilt_deg=tilt,
            rotation_deg=rot,
            aim_point=aim_point,
        )

    @staticmethod
    def four_corner(field: PlayingField, pole_height: float, offset: float) -> List[LightingPole]:
        """
        Place 4 poles at the corners of the field (outside run-off),
        each with one luminaire aimed at the field center.
        """
        aim = (0.0, 0.0, 0.0)
        out: List[LightingPole] = []
        for i, pos in enumerate(PoleLayout._field_corners(field, pole_height, offset), start=1):
            pole = LightingPole(id=f"P{i}", position=pos, luminaires=[])
            pole.luminaires.append(PoleLayout._default_luminaire_at(pole, aim))
            out.append(pole)
        return out

    @staticmethod
    def six_pole(field: PlayingField, pole_height: float, offset: float) -> List[LightingPole]:
        """4 corners + 2 midfield poles."""
        poles = PoleLayout.four_corner(field, pole_height, offset)
        hx = field.total_length / 2.0 + float(offset)
        mid_y = field.total_width / 2.0 + float(offset)
        extras = [(-0.0, -mid_y, pole_height), (0.0, mid_y, pole_height)]
        aim = (0.0, 0.0, 0.0)
        for i, pos in enumerate(extras, start=5):
            pole = LightingPole(id=f"P{i}", position=pos, luminaires=[])
            pole.luminaires.append(PoleLayout._default_luminaire_at(pole, aim))
            poles.append(pole)
        return poles

    @staticmethod
    def eight_pole(field: PlayingField, pole_height: float, offset: float) -> List[LightingPole]:
        """4 corners + 2 per side at thirds."""
        poles = PoleLayout.four_corner(field, pole_height, offset)
        hx = field.total_length / 2.0 + float(offset)
        hy = field.total_width / 2.0 + float(offset)
        x1 = -hx / 3.0
        x2 = hx / 3.0
        extras = [(x1, -hy, pole_height), (x2, -hy, pole_height), (x1, hy, pole_height), (x2, hy, pole_height)]
        aim = (0.0, 0.0, 0.0)
        for i, pos in enumerate(extras, start=5):
            pole = LightingPole(id=f"P{i}", position=pos, luminaires=[])
            pole.luminaires.append(PoleLayout._default_luminaire_at(pole, aim))
            poles.append(pole)
        return poles

    @staticmethod
    def compute_aiming(pole: LightingPole, aim_point: Tuple[float, float, float]) -> Tuple[float, float]:
        """
        Given pole position and aim point, compute (tilt_deg, rotation_deg).
        rotation_deg is azimuth from +Y clockwise; tilt_deg is down-angle from horizontal.
        """
        px, py, pz = (float(v) for v in pole.position)
        ax, ay, az = (float(v) for v in aim_point)
        dx = ax - px
        dy = ay - py
        dz = pz - az
        horiz = math.hypot(dx, dy)
        tilt = math.degrees(math.atan2(max(dz, 0.0), max(horiz, 1e-9)))
        rotation = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
        return tilt, rotation

