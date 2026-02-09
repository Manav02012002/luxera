from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any

from luxera.project.schema import Project, JobSpec
from luxera.project.diff import ProjectDiff
from luxera.runner import run_job


@dataclass(frozen=True)
class SimulationResult:
    summary: Dict[str, Any]


def simulate_diff(project: Project, job_id: str, diff: ProjectDiff) -> SimulationResult:
    # Clone by reusing in-memory project for now; apply diff and run job
    diff.apply(project)
    ref = run_job(project, job_id)
    return SimulationResult(summary=ref.summary)
