from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from luxera.optim.optimizer import run_optimizer
from luxera.project.diff import DiffOp, ProjectDiff


@dataclass(frozen=True)
class OptimizeSkillOutput:
    plan: str
    diff: ProjectDiff
    run_manifest: Dict[str, object]


def build_optimize_skill(
    project_path: str,
    job_id: str,
    candidate_limit: int = 12,
    constraints: Dict[str, float] | None = None,
) -> OptimizeSkillOutput:
    artifacts = run_optimizer(
        project_path,
        job_id=job_id,
        candidate_limit=max(1, int(candidate_limit)),
        constraints=constraints,
    )
    best_diff_payload = json.loads(Path(artifacts.best_diff_json).read_text(encoding="utf-8"))
    ops = []
    for raw in best_diff_payload.get("ops", []):
        if not isinstance(raw, dict):
            continue
        ops.append(
            DiffOp(
                op=str(raw.get("op", "update")),  # type: ignore[arg-type]
                kind=str(raw.get("kind", "luminaire")),  # type: ignore[arg-type]
                id=str(raw.get("id", "")),
                payload=raw.get("payload", {}),
            )
        )
    diff = ProjectDiff(ops=ops)
    return OptimizeSkillOutput(
        plan="Evaluate deterministic layout candidates, then propose the best diff for approval.",
        diff=diff,
        run_manifest={
            "skill": "optimize",
            "job_id": job_id,
            "candidate_limit": int(candidate_limit),
            "constraints": constraints or {},
            "artifacts": {
                "candidates_csv": artifacts.candidates_csv,
                "topk_csv": artifacts.topk_csv,
                "best_diff_json": artifacts.best_diff_json,
                "optimizer_manifest_json": artifacts.optimizer_manifest_json,
            },
        },
    )
