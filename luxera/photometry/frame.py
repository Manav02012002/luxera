from __future__ import annotations

import numpy as np
from typing import Literal, Tuple

from luxera.geometry.core import Vector3
from luxera.core.types import Transform
from luxera.photometry.sample import world_to_luminaire_local_direction, direction_to_photometric_angles


def world_dir_to_photometric_angles(
    transform: Transform,
    world_dir: Vector3,
    system: Literal["C", "B", "A"],
    vertical_angles: list[float] | None = None,
) -> Tuple[float, float]:
    local_dir = world_to_luminaire_local_direction(transform, world_dir)
    va = np.array(vertical_angles, dtype=float) if vertical_angles is not None else None
    return direction_to_photometric_angles(local_dir, system, va)
