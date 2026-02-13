from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


UpAxis = Literal["Z_UP", "Y_UP"]
Handedness = Literal["RIGHT_HANDED", "LEFT_HANDED"]


@dataclass(frozen=True)
class AxisConvention:
    up_axis: UpAxis = "Z_UP"
    handedness: Handedness = "RIGHT_HANDED"


@dataclass(frozen=True)
class AxisTransformReport:
    axis_transform_applied: str
    matrix: list[list[float]]


def axis_conversion_matrix(source: AxisConvention, target: AxisConvention = AxisConvention()) -> np.ndarray:
    # Canonical target default: right-handed Z-up.
    m = np.eye(4, dtype=float)
    if source.up_axis != target.up_axis:
        # Y-up -> Z-up rotation about +X by -90 degrees.
        if source.up_axis == "Y_UP" and target.up_axis == "Z_UP":
            rot = np.array(
                [
                    [1.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, -1.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ],
                dtype=float,
            )
            m = rot @ m
        elif source.up_axis == "Z_UP" and target.up_axis == "Y_UP":
            rot = np.array(
                [
                    [1.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, -1.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ],
                dtype=float,
            )
            m = rot @ m
    if source.handedness != target.handedness:
        # Mirror X to switch handedness.
        flip = np.diag([-1.0, 1.0, 1.0, 1.0])
        m = flip @ m
    return m


def apply_axis_conversion(points: np.ndarray, matrix4: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("points must be shape (N,3)")
    h = np.ones((pts.shape[0], 4), dtype=float)
    h[:, :3] = pts
    out = (np.asarray(matrix4, dtype=float) @ h.T).T
    return out[:, :3]


def describe_axis_conversion(source: AxisConvention, target: AxisConvention = AxisConvention()) -> AxisTransformReport:
    m = axis_conversion_matrix(source, target)
    label = f"{source.up_axis}/{source.handedness}->{target.up_axis}/{target.handedness}"
    return AxisTransformReport(axis_transform_applied=label, matrix=[[float(v) for v in row] for row in m.tolist()])
