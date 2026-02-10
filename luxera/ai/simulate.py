from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any

from pathlib import Path

from luxera.project.diff import ProjectDiff
from luxera.project.io import load_project_schema, save_project_schema
from luxera.runner import run_job


@dataclass(frozen=True)
class SimulationResult:
    summary: Dict[str, Any]


def simulate_diff(project_path: str | Path, job_id: str, diff: ProjectDiff) -> SimulationResult:
    """
    Apply a diff to a project file and execute a path-based simulation run.
    """
    ppath = Path(project_path).expanduser().resolve()
    project = load_project_schema(ppath)
    diff.apply(project)
    save_project_schema(project, ppath)
    ref = run_job(ppath, job_id)
    return SimulationResult(summary=ref.summary)
