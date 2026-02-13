from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Sequence, Tuple

from luxera.geometry.core import Material
from luxera.project.schema import MaterialSpec, SurfaceSpec


@dataclass(frozen=True)
class MaterialOptics:
    diffuse_reflectance_rgb: Tuple[float, float, float]
    specular_reflectance: float
    roughness: Optional[float]
    transmittance: float


@dataclass(frozen=True)
class WallSideMaterials:
    side_a: Optional[str] = None
    side_b: Optional[str] = None


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _resolve_diffuse_rgb(spec: MaterialSpec) -> Tuple[float, float, float]:
    rgb: Optional[Sequence[float]] = spec.diffuse_reflectance_rgb or spec.reflectance_rgb
    if rgb is None or len(rgb) != 3:
        r = _clamp01(spec.reflectance)
        return (r, r, r)
    return (_clamp01(float(rgb[0])), _clamp01(float(rgb[1])), _clamp01(float(rgb[2])))


def material_optics_from_spec(spec: MaterialSpec) -> MaterialOptics:
    diffuse = _resolve_diffuse_rgb(spec)
    # Keep backward compatibility with prior "specularity" field.
    specular = _clamp01(spec.specular_reflectance if spec.specular_reflectance is not None else spec.specularity)
    roughness = None if spec.roughness is None else _clamp01(spec.roughness)
    transmittance = _clamp01(spec.transmittance)
    return MaterialOptics(
        diffuse_reflectance_rgb=diffuse,
        specular_reflectance=specular,
        roughness=roughness,
        transmittance=transmittance,
    )


def material_from_spec(spec: MaterialSpec, name: Optional[str] = None) -> Material:
    optics = material_optics_from_spec(spec)
    # Diffuse radiosity uses average diffuse reflectance.
    reflectance = sum(optics.diffuse_reflectance_rgb) / 3.0
    return Material(
        name=name or spec.name,
        reflectance=reflectance,
        transmittance=optics.transmittance,
        specularity=optics.specular_reflectance,
        color=optics.diffuse_reflectance_rgb,
    )


def encode_wall_side_material_tags(side_a: Optional[str], side_b: Optional[str]) -> list[str]:
    return [f"wall_material_side_a={side_a or ''}", f"wall_material_side_b={side_b or ''}"]


def material_id_for_surface_side(
    surface: SurfaceSpec,
    *,
    room_id: Optional[str] = None,
    side: Optional[Literal["A", "B"]] = None,
) -> Optional[str]:
    if side == "A":
        return surface.wall_material_side_a or surface.material_id
    if side == "B":
        return surface.wall_material_side_b or surface.material_id
    if room_id is not None:
        if surface.wall_room_side_a == room_id:
            return surface.wall_material_side_a or surface.material_id
        if surface.wall_room_side_b == room_id:
            return surface.wall_material_side_b or surface.material_id
    return surface.material_id or surface.wall_material_side_a or surface.wall_material_side_b
