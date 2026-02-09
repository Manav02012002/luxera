from __future__ import annotations

import math
import numpy as np
from typing import Literal, Tuple

from luxera.geometry.core import Vector3
from luxera.core.types import Transform


def world_dir_to_photometric_angles(
    transform: Transform,
    world_dir: Vector3,
    system: Literal["C", "B", "A"],
    vertical_angles: list[float] | None = None,
) -> Tuple[float, float]:
    # Convert to luminaire local frame
    R = transform.get_rotation_matrix()
    local_dir = Vector3.from_array(R.T @ world_dir.normalize().to_array())

    if system == "C":
        cos_gamma = -local_dir.z
        cos_gamma = max(-1.0, min(1.0, cos_gamma))
        gamma_deg = math.degrees(math.acos(cos_gamma))
        c_deg = (math.degrees(math.atan2(local_dir.y, local_dir.x)) + 360.0) % 360.0
        return c_deg, gamma_deg

    if system in ("A", "B"):
        # Delegate to sampling-style angle derivation using data range if provided
        from luxera.photometry.sample import _angles_from_direction_type_ab
        if vertical_angles is None:
            vertical_angles = [0.0, 90.0, 180.0]
        return _angles_from_direction_type_ab(local_dir, system, np.array(vertical_angles, dtype=float))

    raise NotImplementedError(f"Photometric system {system} not yet supported")
