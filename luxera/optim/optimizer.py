from __future__ import annotations

import copy
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from luxera.design.placement import place_array_rect
from luxera.project.diff import DiffOp, ProjectDiff
from luxera.project.io import load_project_schema
from luxera.project.runner import run_job_in_memory


@dataclass(frozen=True)
class OptimizerCandidate:
    index: int
    nx: int
    ny: int
    spacing_scale: float
    mounting_height: float
    dimming: float
    fixture_count: int
    mean_lux: float
    uniformity_ratio: float
    ugr_worst_case: Optional[float]
    feasible: bool
    objective: float


@dataclass(frozen=True)
class OptimizerArtifacts:
    candidates_csv: str
    topk_csv: str
    best_diff_json: str
    optimizer_manifest_json: str


def _objective(summary: Dict[str, float], fixture_count: int, dimming: float, constraints: Dict[str, float]) -> tuple[bool, float]:
    target = float(constraints.get("target_lux", 500.0))
    umin = float(constraints.get("uniformity_min", 0.4))
    ugr_max = float(constraints.get("ugr_max", 19.0))
    mean_lux = float(summary.get("mean_lux", 0.0))
    u0 = float(summary.get("uniformity_ratio", 0.0))
    ugr = summary.get("ugr_worst_case")
    feasible = mean_lux >= target and u0 >= umin and (not isinstance(ugr, (int, float)) or float(ugr) <= ugr_max)
    penalty = 0.0
    if mean_lux < target:
        penalty += (target - mean_lux) / max(target, 1e-9) * 100.0
    if u0 < umin:
        penalty += (umin - u0) * 100.0
    if isinstance(ugr, (int, float)) and float(ugr) > ugr_max:
        penalty += (float(ugr) - ugr_max) * 10.0
    objective = fixture_count * dimming + penalty
    return feasible, objective


def run_optimizer(
    project_path: str | Path,
    job_id: str,
    *,
    candidate_limit: int = 12,
    constraints: Optional[Dict[str, float]] = None,
) -> OptimizerArtifacts:
    ppath = Path(project_path).expanduser().resolve()
    base = load_project_schema(ppath)
    if not base.geometry.rooms:
        raise ValueError("Optimizer requires at least one room")
    if not base.photometry_assets:
        raise ValueError("Optimizer requires at least one photometry asset")
    room = base.geometry.rooms[0]
    asset_id = base.photometry_assets[0].id
    c = constraints or {"target_lux": 500.0, "uniformity_min": 0.4, "ugr_max": 19.0}

    nx_values = [2, 3, 4]
    ny_values = [2, 3, 4]
    spacing_scales = [0.8, 1.0]
    mount_heights = [room.height * 0.8, room.height * 0.9]
    dimming_values = [0.7, 0.85, 1.0]

    candidates: List[OptimizerCandidate] = []
    idx = 0
    for nx in nx_values:
        for ny in ny_values:
            for scale in spacing_scales:
                for mh in mount_heights:
                    for dim in dimming_values:
                        if idx >= candidate_limit:
                            break
                        idx += 1
                        cand = copy.deepcopy(base)
                        margin = 0.6 * scale
                        arr = place_array_rect(
                            room_bounds=(room.origin[0], room.origin[1], room.origin[0] + room.width, room.origin[1] + room.length),
                            nx=nx,
                            ny=ny,
                            margin_x=margin,
                            margin_y=margin,
                            z=room.origin[2] + mh,
                            photometry_asset_id=asset_id,
                        )
                        for lum in arr:
                            lum.flux_multiplier = float(dim)
                        cand.luminaires = arr
                        cand.results = []
                        ref = run_job_in_memory(cand, job_id)
                        summary = ref.summary or {}
                        feasible, obj = _objective(summary, len(arr), float(dim), c)
                        candidates.append(
                            OptimizerCandidate(
                                index=idx,
                                nx=nx,
                                ny=ny,
                                spacing_scale=float(scale),
                                mounting_height=float(mh),
                                dimming=float(dim),
                                fixture_count=len(arr),
                                mean_lux=float(summary.get("mean_lux", 0.0)),
                                uniformity_ratio=float(summary.get("uniformity_ratio", 0.0)),
                                ugr_worst_case=float(summary["ugr_worst_case"]) if isinstance(summary.get("ugr_worst_case"), (int, float)) else None,
                                feasible=feasible,
                                objective=obj,
                            )
                        )
                    if idx >= candidate_limit:
                        break
                if idx >= candidate_limit:
                    break
            if idx >= candidate_limit:
                break
        if idx >= candidate_limit:
            break

    ranked = sorted(candidates, key=lambda x: (not x.feasible, x.objective))
    topk = ranked[: min(5, len(ranked))]
    best = topk[0]

    out_dir = ppath.parent / ".luxera" / "optimizer"
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates_csv = out_dir / "candidates.csv"
    topk_csv = out_dir / "topk.csv"
    best_diff_json = out_dir / "best_diff.json"
    manifest_json = out_dir / "optimizer_manifest.json"

    with candidates_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(candidates[0]).keys()) if candidates else ["index"])
        w.writeheader()
        for row in candidates:
            w.writerow(asdict(row))
    with topk_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(topk[0]).keys()) if topk else ["index"])
        w.writeheader()
        for row in topk:
            w.writerow(asdict(row))

    best_layout = place_array_rect(
        room_bounds=(room.origin[0], room.origin[1], room.origin[0] + room.width, room.origin[1] + room.length),
        nx=best.nx,
        ny=best.ny,
        margin_x=0.6 * best.spacing_scale,
        margin_y=0.6 * best.spacing_scale,
        z=room.origin[2] + best.mounting_height,
        photometry_asset_id=asset_id,
    )
    for lum in best_layout:
        lum.flux_multiplier = best.dimming
    ops = [DiffOp(op="remove", kind="luminaire", id=l.id) for l in base.luminaires]
    ops.extend(DiffOp(op="add", kind="luminaire", id=l.id, payload=l) for l in best_layout)
    best_diff = ProjectDiff(ops=ops)
    best_diff_json.write_text(json.dumps({"ops": [asdict(op) for op in best_diff.ops]}, indent=2, sort_keys=True), encoding="utf-8")

    manifest_json.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "constraints": c,
                "candidate_limit": candidate_limit,
                "best": asdict(best),
                "artifacts": {
                    "candidates_csv": str(candidates_csv),
                    "topk_csv": str(topk_csv),
                    "best_diff_json": str(best_diff_json),
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return OptimizerArtifacts(
        candidates_csv=str(candidates_csv),
        topk_csv=str(topk_csv),
        best_diff_json=str(best_diff_json),
        optimizer_manifest_json=str(manifest_json),
    )
