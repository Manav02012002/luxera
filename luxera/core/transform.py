from __future__ import annotations

from typing import Optional
import numpy as np

from luxera.geometry.core import Vector3, Transform


def from_euler_zyx(
    position: Vector3,
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
    scale: Optional[Vector3] = None,
) -> Transform:
    """
    Build a transform from Euler ZYX rotation in degrees.

    Convention reference: docs/spec/coordinate_conventions.md
    """
    return Transform.from_euler_zyx(position, yaw_deg, pitch_deg, roll_deg, scale=scale)


def from_aim_up(
    position: Vector3,
    aim: Vector3,
    up: Vector3,
    scale: Optional[Vector3] = None,
) -> Transform:
    """
    Build a transform from aim/up vectors.

    Convention reference: docs/spec/coordinate_conventions.md
    """
    return Transform.from_aim_up(position, aim, up, scale=scale)


__all__ = ["Transform", "Vector3", "from_euler_zyx", "from_aim_up"]
