from __future__ import annotations

from typing import List, Tuple

from luxera.geometry.scene_prep import clean_scene_surfaces
from luxera.project.schema import SurfaceSpec


def clean_ifc_surfaces(surfaces: List[SurfaceSpec]) -> Tuple[List[SurfaceSpec], dict]:
    cleaned, report = clean_scene_surfaces(surfaces)
    payload = report.to_dict() if hasattr(report, "to_dict") else report.__dict__
    return cleaned, payload
