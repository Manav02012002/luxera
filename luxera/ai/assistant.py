from __future__ import annotations

import uuid
from typing import Dict, Any

from luxera.project.diff import ProjectDiff, DiffOp
from luxera.project.schema import Project
from luxera.optim.layout import propose_layout


def propose_luminaire_layout(project: Project, target_lux: float, constraints: Dict[str, Any] | None = None) -> ProjectDiff:
    constraints = constraints or {}
    max_rows = int(constraints.get("max_rows", 6))
    max_cols = int(constraints.get("max_cols", 6))

    layout, _ = propose_layout(project, target_lux, max_rows=max_rows, max_cols=max_cols)

    ops = []
    # remove existing luminaires
    for lum in project.luminaires:
        ops.append(DiffOp(op="remove", kind="luminaire", id=lum.id))

    # add new luminaires
    for inst in layout:
        inst.id = str(uuid.uuid4())
        ops.append(DiffOp(op="add", kind="luminaire", id=inst.id, payload=inst))

    return ProjectDiff(ops=ops)
