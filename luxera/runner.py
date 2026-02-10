from __future__ import annotations

from pathlib import Path
from typing import Union
import warnings

from luxera.project.runner import RunnerError, run_job as run_job_path, run_job_in_memory as _run_job_in_memory


def run_job(project_path: Union[str, Path], job_id: str):
    return run_job_path(project_path, job_id)


def run_job_in_memory(project, job_id: str):
    warnings.warn(
        "luxera.runner.run_job_in_memory is deprecated; use run_job(project_path, job_id) "
        "for explicit persistence semantics.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _run_job_in_memory(project, job_id)


__all__ = ["RunnerError", "run_job", "run_job_in_memory"]
