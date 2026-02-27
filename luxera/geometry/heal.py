from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from luxera.geometry.cleaning import fix_winding_consistent_normals, merge_vertices, remove_degenerate_triangles
from luxera.geometry.tolerance import EPS_AREA, EPS_POS, EPS_SLIVER_RATIO, EPS_WELD

Point3 = Tuple[float, float, float]
TriangleIdx = Tuple[int, int, int]


@dataclass(frozen=True)
class FaceRef:
    object_id: Optional[str] = None
    face_id: Optional[str] = None
    triangle_index: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {}
        if self.object_id is not None:
            out["object_id"] = str(self.object_id)
        if self.face_id is not None:
            out["face_id"] = str(self.face_id)
        if self.triangle_index is not None:
            out["triangle_index"] = int(self.triangle_index)
        return out


@dataclass(frozen=True)
class HealAction:
    action: str
    details: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {"action": self.action, "details": dict(self.details)}


@dataclass(frozen=True)
class MeshHealingReport:
    epsilons: Dict[str, float]
    counts: Dict[str, int]
    issues: Dict[str, List[Dict[str, object]]]
    actions: List[HealAction]
    input: Dict[str, int]
    output: Dict[str, int]
    cleaned_mesh_hash: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "epsilons": dict(self.epsilons),
            "counts": dict(self.counts),
            "issues": {k: list(v) for k, v in self.issues.items()},
            "actions": [a.to_dict() for a in self.actions],
            "input": dict(self.input),
            "output": dict(self.output),
            "cleaned_mesh_hash": self.cleaned_mesh_hash,
        }


@dataclass(frozen=True)
class MeshHealingResult:
    vertices: List[Point3]
    triangles: List[TriangleIdx]
    triangle_refs: List[FaceRef]
    report: MeshHealingReport


def _tri_area(verts: np.ndarray, tri: TriangleIdx) -> float:
    a, b, c = tri
    va, vb, vc = verts[a], verts[b], verts[c]
    return 0.5 * float(np.linalg.norm(np.cross(vb - va, vc - va)))


def _tri_edges(tri: TriangleIdx) -> Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]:
    a, b, c = tri
    return (
        (a, b) if a < b else (b, a),
        (b, c) if b < c else (c, b),
        (c, a) if c < a else (a, c),
    )


def _edge_incidence(triangles: Sequence[TriangleIdx]) -> Dict[Tuple[int, int], List[int]]:
    out: Dict[Tuple[int, int], List[int]] = {}
    for tidx, tri in enumerate(triangles):
        for edge in _tri_edges(tri):
            out.setdefault(edge, []).append(tidx)
    return out


def _segment_intersects_triangle(p0: np.ndarray, p1: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> bool:
    d = p1 - p0
    e1 = b - a
    e2 = c - a
    pvec = np.cross(d, e2)
    det = float(np.dot(e1, pvec))
    if abs(det) < EPS_POS:
        return False
    inv_det = 1.0 / det
    tvec = p0 - a
    u = float(np.dot(tvec, pvec) * inv_det)
    if u < 0.0 or u > 1.0:
        return False
    qvec = np.cross(tvec, e1)
    v = float(np.dot(d, qvec) * inv_det)
    if v < 0.0 or (u + v) > 1.0:
        return False
    t = float(np.dot(e2, qvec) * inv_det)
    return 0.0 <= t <= 1.0


def _coarse_self_intersections(verts: np.ndarray, triangles: Sequence[TriangleIdx]) -> List[Tuple[int, int]]:
    tris = list(triangles)
    if len(tris) < 2:
        return []
    boxes: List[Tuple[np.ndarray, np.ndarray]] = []
    for a, b, c in tris:
        pts = np.vstack((verts[a], verts[b], verts[c]))
        boxes.append((pts.min(axis=0), pts.max(axis=0)))
    hits: List[Tuple[int, int]] = []
    for i in range(len(tris)):
        ai, bi, ci = tris[i]
        set_i = {ai, bi, ci}
        v1 = (verts[ai], verts[bi], verts[ci])
        for j in range(i + 1, len(tris)):
            aj, bj, cj = tris[j]
            if set_i.intersection({aj, bj, cj}):
                continue
            mn_i, mx_i = boxes[i]
            mn_j, mx_j = boxes[j]
            if np.any(mx_i < mn_j) or np.any(mx_j < mn_i):
                continue
            v2 = (verts[aj], verts[bj], verts[cj])
            edges1 = ((v1[0], v1[1]), (v1[1], v1[2]), (v1[2], v1[0]))
            edges2 = ((v2[0], v2[1]), (v2[1], v2[2]), (v2[2], v2[0]))
            if any(_segment_intersects_triangle(e0, e1, v2[0], v2[1], v2[2]) for e0, e1 in edges1):
                hits.append((i, j))
                continue
            if any(_segment_intersects_triangle(e0, e1, v1[0], v1[1], v1[2]) for e0, e1 in edges2):
                hits.append((i, j))
    return hits


def _stable_mesh_hash(vertices: Sequence[Point3], triangles: Sequence[TriangleIdx]) -> str:
    payload = {
        "vertices": [[float(f"{x:.12g}"), float(f"{y:.12g}"), float(f"{z:.12g}")] for (x, y, z) in vertices],
        "triangles": [[int(a), int(b), int(c)] for (a, b, c) in triangles],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def heal_mesh(
    vertices: Sequence[Point3],
    triangles: Sequence[TriangleIdx],
    *,
    triangle_refs: Optional[Sequence[Mapping[str, object] | FaceRef]] = None,
    weld_epsilon: float = EPS_WELD,
    area_epsilon: float = EPS_AREA,
    sliver_ratio_epsilon: float = EPS_SLIVER_RATIO,
    normal_epsilon: float = EPS_POS,
    deduplicate_coplanar_faces: bool = True,
) -> MeshHealingResult:
    in_vertices = [(float(x), float(y), float(z)) for (x, y, z) in vertices]
    in_triangles = [(int(a), int(b), int(c)) for (a, b, c) in triangles]

    refs_in: List[FaceRef] = []
    if triangle_refs is None:
        refs_in = [FaceRef(triangle_index=i) for i in range(len(in_triangles))]
    else:
        for i, r in enumerate(triangle_refs):
            if isinstance(r, FaceRef):
                refs_in.append(r)
            elif isinstance(r, Mapping):
                refs_in.append(
                    FaceRef(
                        object_id=str(r.get("object_id")) if r.get("object_id") is not None else None,
                        face_id=str(r.get("face_id")) if r.get("face_id") is not None else None,
                        triangle_index=(int(r.get("triangle_index")) if r.get("triangle_index") is not None else i),
                    )
                )
            else:
                refs_in.append(FaceRef(triangle_index=i))
    if len(refs_in) != len(in_triangles):
        refs_in = [FaceRef(triangle_index=i) for i in range(len(in_triangles))]

    actions: List[HealAction] = []
    issues: Dict[str, List[Dict[str, object]]] = {
        "non_manifold_edges": [],
        "degenerate_triangles": [],
        "inverted_normals": [],
        "duplicate_coplanar_faces": [],
        "sliver_triangles": [],
        "self_intersections_coarse": [],
        "open_shell_edges": [],
    }

    merged_vertices, remap = merge_vertices(in_vertices, eps=float(weld_epsilon))
    merged = [tuple(v) for v in merged_vertices]
    triangles_remapped = [(remap[a], remap[b], remap[c]) for (a, b, c) in in_triangles]
    if len(merged) != len(in_vertices):
        actions.append(
            HealAction(
                action="merge_near_duplicate_vertices",
                details={"before": len(in_vertices), "after": len(merged), "merged": len(in_vertices) - len(merged)},
            )
        )

    verts_np = np.asarray(merged, dtype=float) if merged else np.zeros((0, 3), dtype=float)
    degenerate_idxs: List[int] = []
    for idx, (a, b, c) in enumerate(triangles_remapped):
        is_deg = (a == b) or (b == c) or (a == c)
        if not is_deg and verts_np.size:
            is_deg = _tri_area(verts_np, (a, b, c)) <= float(area_epsilon)
        if is_deg:
            degenerate_idxs.append(idx)
            issues["degenerate_triangles"].append(refs_in[idx].to_dict())

    triangles_clean = [t for i, t in enumerate(triangles_remapped) if i not in set(degenerate_idxs)]
    refs_clean = [r for i, r in enumerate(refs_in) if i not in set(degenerate_idxs)]
    if degenerate_idxs:
        actions.append(
            HealAction(
                action="remove_degenerate_triangles",
                details={"removed": len(degenerate_idxs), "before": len(triangles_remapped), "after": len(triangles_clean)},
            )
        )

    # Optionally deduplicate exact coplanar duplicates after weld/remap.
    dedup_tris: List[TriangleIdx] = []
    dedup_refs: List[FaceRef] = []
    dup_count = 0
    seen_faces: Dict[Tuple[int, int, int], int] = {}
    for tri, ref in zip(triangles_clean, refs_clean):
        key = tuple(sorted(tri))
        if key in seen_faces:
            dup_count += 1
            issues["duplicate_coplanar_faces"].append(ref.to_dict())
            if deduplicate_coplanar_faces:
                continue
        seen_faces.setdefault(key, len(dedup_tris))
        dedup_tris.append(tri)
        dedup_refs.append(ref)
    if deduplicate_coplanar_faces and dup_count > 0:
        actions.append(
            HealAction(
                action="deduplicate_coplanar_duplicate_faces",
                details={"removed": int(dup_count), "before": len(triangles_clean), "after": len(dedup_tris)},
            )
        )

    # Sliver + inverted detection pre-winding fix.
    sliver_count = 0
    inverted_count = 0
    for idx, tri in enumerate(dedup_tris):
        a, b, c = tri
        va, vb, vc = verts_np[a], verts_np[b], verts_np[c]
        edges = sorted(
            [
                float(np.linalg.norm(vb - va)),
                float(np.linalg.norm(vc - vb)),
                float(np.linalg.norm(va - vc)),
            ]
        )
        if edges[-1] > 0.0 and edges[0] / edges[-1] < float(sliver_ratio_epsilon):
            sliver_count += 1
            issues["sliver_triangles"].append(dedup_refs[idx].to_dict())
        n = np.cross(vb - va, vc - va)
        cent = (va + vb + vc) / 3.0
        if float(np.dot(n, cent)) < -float(normal_epsilon):
            inverted_count += 1
            issues["inverted_normals"].append(dedup_refs[idx].to_dict())

    wound = fix_winding_consistent_normals(dedup_tris, merged)
    flipped = sum(1 for a, b in zip(dedup_tris, wound) if a != b)
    if flipped > 0:
        actions.append(HealAction(action="unify_winding", details={"flipped": int(flipped)}))

    edge_map = _edge_incidence(wound)
    non_manifold_edges = sorted([e for e, ids in edge_map.items() if len(ids) > 2], key=lambda x: (x[0], x[1]))
    for e in non_manifold_edges:
        issues["non_manifold_edges"].append({"edge": [int(e[0]), int(e[1])], "incident_faces": list(edge_map[e])})

    open_edges = sorted([e for e, ids in edge_map.items() if len(ids) == 1], key=lambda x: (x[0], x[1]))
    for e in open_edges:
        issues["open_shell_edges"].append({"edge": [int(e[0]), int(e[1])], "incident_faces": list(edge_map[e])})

    self_hits = _coarse_self_intersections(verts_np, wound) if verts_np.size and wound else []
    for i, j in self_hits:
        issues["self_intersections_coarse"].append(
            {
                "triangle_a": dedup_refs[i].to_dict() if i < len(dedup_refs) else {"triangle_index": i},
                "triangle_b": dedup_refs[j].to_dict() if j < len(dedup_refs) else {"triangle_index": j},
            }
        )

    counts = {
        "non_manifold_edges": len(non_manifold_edges),
        "degenerate_triangles": len(degenerate_idxs),
        "inverted_normals": int(inverted_count),
        "duplicate_coplanar_faces": int(dup_count),
        "sliver_triangles": int(sliver_count),
        "self_intersections_coarse": len(self_hits),
        "open_shell_edges": len(open_edges),
    }
    report = MeshHealingReport(
        epsilons={
            "weld_epsilon": float(weld_epsilon),
            "area_epsilon": float(area_epsilon),
            "sliver_ratio_epsilon": float(sliver_ratio_epsilon),
            "normal_epsilon": float(normal_epsilon),
        },
        counts=counts,
        issues=issues,
        actions=actions,
        input={"vertices": len(in_vertices), "triangles": len(in_triangles)},
        output={"vertices": len(merged), "triangles": len(wound)},
        cleaned_mesh_hash=_stable_mesh_hash(merged, wound),
    )
    return MeshHealingResult(vertices=merged, triangles=wound, triangle_refs=dedup_refs, report=report)


def triangulate_faces_for_healing(
    faces: Sequence[Sequence[int]],
    *,
    object_id: Optional[str] = None,
    face_prefix: str = "face",
) -> Tuple[List[TriangleIdx], List[FaceRef]]:
    tris: List[TriangleIdx] = []
    refs: List[FaceRef] = []
    for fidx, face in enumerate(faces):
        idx = [int(v) for v in face]
        if len(idx) < 3:
            continue
        for k in range(1, len(idx) - 1):
            tris.append((idx[0], idx[k], idx[k + 1]))
            refs.append(
                FaceRef(
                    object_id=object_id,
                    face_id=f"{face_prefix}_{fidx + 1}",
                    triangle_index=len(tris) - 1,
                )
            )
    return tris, refs
