from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Protocol

from luxera.project.schema import Project, JobSpec


@dataclass(frozen=True)
class BackendRunResult:
    summary: Dict[str, Any]
    assets: Dict[str, str]
    artifacts: Dict[str, str] = field(default_factory=dict)
    result_data: Dict[str, Any] = field(default_factory=dict)


class DirectBackend(Protocol):
    name: str

    def run(self, project: Project, job: JobSpec, out_dir: Path) -> BackendRunResult: ...
