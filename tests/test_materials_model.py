from __future__ import annotations

from luxera.geometry.materials import material_from_spec, material_optics_from_spec
from luxera.project.schema import MaterialSpec


def test_material_optics_prefers_new_fields() -> None:
    spec = MaterialSpec(
        id="m1",
        name="M",
        reflectance=0.4,
        specularity=0.1,
        diffuse_reflectance_rgb=(0.2, 0.4, 0.6),
        specular_reflectance=0.3,
        roughness=0.8,
        transmittance=0.2,
    )
    o = material_optics_from_spec(spec)
    assert o.diffuse_reflectance_rgb == (0.2, 0.4, 0.6)
    assert o.specular_reflectance == 0.3
    assert o.roughness == 0.8
    assert o.transmittance == 0.2


def test_material_from_spec_maps_to_core_material() -> None:
    spec = MaterialSpec(id="m2", name="M2", reflectance=0.9, diffuse_reflectance_rgb=(0.3, 0.3, 0.6), transmittance=0.1)
    m = material_from_spec(spec)
    assert abs(m.reflectance - 0.4) < 1e-9
    assert abs(m.transmittance - 0.1) < 1e-9

