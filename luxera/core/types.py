from __future__ import annotations

from typing import Optional
import numpy as np

from luxera.geometry.core import Vector3, Transform


Rotation = np.ndarray  # 3x3 rotation matrix

__all__ = ["Vector3", "Transform", "Rotation"]
