from __future__ import annotations

from luxera.engine.direct_illuminance import build_direct_occlusion_context
from luxera.geometry.bvh import any_hit
from luxera.geometry.core import Vector3
from luxera.geometry.ray_config import scaled_ray_policy
from luxera.ops.scene_ops import place_opening_on_wall
from luxera.project.schema import Project, SurfaceSpec


def _ray_hit(ctx, a: Vector3, b: Vector3) -> bool:
    d = b - a
    dist = d.length()
    assert dist > 0.0
    ray = d / dist
    pol = scaled_ray_policy(scene_scale=dist, user_eps=1e-6)
    origin = a + ray * pol.origin_eps
    t_max = max((b - origin).length() - pol.t_min, 0.0)
    if ctx.bvh is None:
        return False
    return any_hit(ctx.bvh, origin, ray, t_min=pol.t_min, t_max=t_max)


def test_occlusion_rays_see_opening_as_void() -> None:
    p = Project(name="opening-void-occlusion")
    p.geometry.surfaces.append(
        SurfaceSpec(
            id="wall1",
            name="Wall",
            kind="wall",
            vertices=[(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 3.0), (0.0, 0.0, 3.0)],
        )
    )
    place_opening_on_wall(
        p,
        opening_id="o1",
        host_surface_id="wall1",
        width=1.0,
        height=1.2,
        sill_height=0.9,
        distance_from_corner=1.4,
        opening_type="window",
        glazing_material_id="glass",
    )
    ctx = build_direct_occlusion_context(p)

    through_opening = _ray_hit(ctx, Vector3(1.9, -1.0, 1.5), Vector3(1.9, 1.0, 1.5))
    through_solid = _ray_hit(ctx, Vector3(0.4, -1.0, 1.5), Vector3(0.4, 1.0, 1.5))
    assert through_opening is False
    assert through_solid is True
