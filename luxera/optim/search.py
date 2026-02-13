from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

from luxera.project.runner import run_job_in_memory
from luxera.project.io import load_project_schema
from luxera.project.schema import LuminaireInstance, RotationSpec, TransformSpec


@dataclass(frozen=True)
class SearchCandidate:
    rank: int
    rows: int
    cols: int
    dimming: float
    num_luminaires: int
    mean_lux: float
    uniformity_ratio: float
    ugr_worst_case: Optional[float]
    power_proxy: float
    penalty: float
    score: float


@dataclass(frozen=True)
class SearchResult:
    best: SearchCandidate
    top: List[SearchCandidate]
    artifact_json: str
    best_layout: List[LuminaireInstance]


def _build_layout(project, rows: int, cols: int, dimming: float) -> List[LuminaireInstance]:
    if not project.geometry.rooms:
        raise ValueError("Optimizer requires at least one room")
    if not project.photometry_assets:
        raise ValueError("Optimizer requires at least one photometry asset")
    room = project.geometry.rooms[0]
    asset_id = project.photometry_assets[0].id
    z = room.origin[2] + room.height * 0.9
    margin_x = room.width * 0.1
    margin_y = room.length * 0.1
    usable_w = max(0.1, room.width - 2 * margin_x)
    usable_l = max(0.1, room.length - 2 * margin_y)
    dx = usable_w / max(cols, 1)
    dy = usable_l / max(rows, 1)
    start_x = room.origin[0] + margin_x + dx / 2.0
    start_y = room.origin[1] + margin_y + dy / 2.0
    out: List[LuminaireInstance] = []
    for r in range(rows):
        for c in range(cols):
            x = start_x + c * dx
            y = start_y + r * dy
            out.append(
                LuminaireInstance(
                    id=f"opt_{r}_{c}_{uuid.uuid4().hex[:6]}",
                    name=f"Optimized {r+1}-{c+1}",
                    photometry_asset_id=asset_id,
                    transform=TransformSpec(position=(x, y, z), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
                    flux_multiplier=float(dimming),
                )
            )
    return out


def _score(summary: Dict[str, float], constraints: Dict[str, float], num_luminaires: int, dimming: float) -> tuple[float, float, float]:
    mean_lux = float(summary.get("mean_lux", 0.0))
    uniformity = float(summary.get("uniformity_ratio", 0.0))
    ugr = summary.get("ugr_worst_case")
    ugr_v = float(ugr) if isinstance(ugr, (int, float)) else None

    target = float(constraints.get("target_lux", 500.0))
    u0_min = float(constraints.get("uniformity_min", 0.4))
    ugr_max = float(constraints.get("ugr_max", 19.0))

    power_proxy = float(num_luminaires) * float(dimming)
    penalty = abs(mean_lux - target) / max(target, 1e-9) * 10.0
    if uniformity < u0_min:
        penalty += (u0_min - uniformity) * 50.0
    if ugr_v is not None and ugr_v > ugr_max:
        penalty += (ugr_v - ugr_max) * 5.0
    return power_proxy + penalty, power_proxy, penalty


def run_deterministic_search(
    project_path: str | Path,
    job_id: str,
    *,
    max_rows: int = 6,
    max_cols: int = 6,
    dimming_levels: Optional[List[float]] = None,
    constraints: Optional[Dict[str, float]] = None,
    top_n: int = 8,
) -> SearchResult:
    ppath = Path(project_path).expanduser().resolve()
    base = load_project_schema(ppath)
    dim_levels = dimming_levels or [0.6, 0.8, 1.0]
    c = constraints or {"target_lux": 500.0, "uniformity_min": 0.4, "ugr_max": 19.0}

    rows: List[SearchCandidate] = []
    best_layout: List[LuminaireInstance] = []

    for r in range(1, max_rows + 1):
        for ccount in range(1, max_cols + 1):
            for dim in dim_levels:
                cand_project = copy.deepcopy(base)
                layout = _build_layout(cand_project, r, ccount, float(dim))
                cand_project.luminaires = layout
                cand_project.results = []
                ref = run_job_in_memory(cand_project, job_id)
                summary = ref.summary or {}
                score, power_proxy, penalty = _score(summary, c, len(layout), float(dim))
                row = SearchCandidate(
                    rank=0,
                    rows=r,
                    cols=ccount,
                    dimming=float(dim),
                    num_luminaires=len(layout),
                    mean_lux=float(summary.get("mean_lux", 0.0)),
                    uniformity_ratio=float(summary.get("uniformity_ratio", 0.0)),
                    ugr_worst_case=float(summary["ugr_worst_case"]) if isinstance(summary.get("ugr_worst_case"), (int, float)) else None,
                    power_proxy=power_proxy,
                    penalty=penalty,
                    score=score,
                )
                rows.append(row)
                if not best_layout or score < min(x.score for x in rows):
                    best_layout = layout

    ranked = sorted(rows, key=lambda x: x.score)
    ranked = [SearchCandidate(rank=i + 1, **{k: v for k, v in asdict(ca).items() if k != "rank"}) for i, ca in enumerate(ranked)]
    top = ranked[: max(1, int(top_n))]
    best = top[0]

    out_dir = ppath.parent / ".luxera" / "optim"
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / f"search_{job_id}_{uuid.uuid4().hex[:8]}.json"
    payload = {
        "job_id": job_id,
        "constraints": c,
        "top": [asdict(x) for x in top],
        "best": asdict(best),
    }
    artifact.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return SearchResult(best=best, top=top, artifact_json=str(artifact), best_layout=best_layout)
