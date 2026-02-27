from __future__ import annotations

import json
from pathlib import Path

from luxera.agent.context import context_memory_path
from luxera.cli import main
from luxera.project.io import save_project_schema
from luxera.project.schema import JobSpec, Project


def _seed_project(tmp_path: Path) -> Path:
    p = Project(name="CliCtx", root_dir=str(tmp_path))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    path = tmp_path / "p.json"
    save_project_schema(p, path)
    return path


def test_cli_agent_context_show_and_reset(tmp_path: Path) -> None:
    project_path = _seed_project(tmp_path)
    rc_show_1 = main(["agent", "context", "show", str(project_path)])
    assert rc_show_1 == 0

    rc_reset = main(["agent", "context", "reset", str(project_path)])
    assert rc_reset == 0
    mem_path = context_memory_path(project_path)
    payload = json.loads(mem_path.read_text(encoding="utf-8"))
    assert payload.get("turn_count") == 0

    rc_show_2 = main(["agent", "context", "show", str(project_path)])
    assert rc_show_2 == 0
