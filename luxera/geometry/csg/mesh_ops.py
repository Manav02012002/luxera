from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from luxera.geometry.csg.ops import CSGResult, eval_csg
from luxera.geometry.csg.tree import CSGExpr, SolidNode
from luxera.geometry.doctor import repair_mesh
from luxera.geometry.mesh import TriMesh, extrusion_to_trimesh
from luxera.geometry.primitives import Extrusion, Polygon2D


@dataclass(frozen=True)
class MeshBooleanResult:
    ok: bool
    mesh: TriMesh | None = None
    message: str = ""


def _solid_to_mesh(s: SolidNode) -> TriMesh:
    profile = [(float(x), float(y)) for x, y in s.params.get("profile", [])]
    z0 = float(s.params.get("z0", 0.0))
    z1 = float(s.params.get("z1", z0))
    h = float(z1 - z0)
    if len(profile) < 3 or h <= 0.0:
        raise ValueError("invalid extrusion solid")
    return extrusion_to_trimesh(Extrusion(profile2d=Polygon2D(points=profile), height=h), z0=z0)


def _merge_meshes(meshes: List[TriMesh]) -> TriMesh:
    verts: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    offset = 0
    for m in meshes:
        verts.extend(list(m.vertices))
        faces.extend([(a + offset, b + offset, c + offset) for a, b, c in m.faces])
        offset += len(m.vertices)
    out = TriMesh(vertices=verts, faces=faces)
    out.validate()
    return out


def mesh_boolean_with_repair_gate(expr: CSGExpr) -> MeshBooleanResult:
    res: CSGResult = eval_csg(expr)
    if not res.ok:
        return MeshBooleanResult(ok=False, message=(res.error.message if res.error is not None else "csg failed"))

    try:
        meshes = [_solid_to_mesh(s) for s in res.solids]
        merged = _merge_meshes(meshes)
        repaired = repair_mesh(merged.vertices, merged.faces)
        if repaired.report.errors:
            return MeshBooleanResult(ok=False, message="repair gate failed")
        out = TriMesh(vertices=repaired.vertices, faces=repaired.triangles, normals=repaired.normals)
        out.validate()
        return MeshBooleanResult(ok=True, mesh=out)
    except Exception as exc:
        return MeshBooleanResult(ok=False, message=str(exc))
