from __future__ import annotations

import numpy as np
from typing import Dict, Literal, Tuple

from luxera.geometry.core import Vector3
from luxera.core.types import Transform
from luxera.photometry.sample import world_dir_to_photometric_angles as _world_dir_to_photometric_angles


def world_dir_to_photometric_angles(
    world_dir: Vector3,
    transform: Transform,
    orientation: Dict[str, str] | None,
    system: Literal["C", "B", "A"],
    vertical_angles: list[float] | None = None,
) -> Tuple[float, float]:
    """
    Convert world-space direction to photometric angles in the luminaire frame.

    Convention reference: docs/spec/coordinate_conventions.md
    """
    va = np.array(vertical_angles, dtype=float) if vertical_angles is not None else None
    return _world_dir_to_photometric_angles(world_dir, transform, orientation, system, va)
