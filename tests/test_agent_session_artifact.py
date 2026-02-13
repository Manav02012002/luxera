from __future__ import annotations

import json
from pathlib import Path

from luxera.agent.runtime import AgentRuntime
from luxera.project.io import save_project_schema
from luxera.project.schema import JobSpec, Project


def test_runtime_emits_session_artifact(tmp_path: Path) -> None:
    project = Project(name="sess", root_dir=str(tmp_path))
    project.jobs.append(JobSpec(id="j1", type="direct"))
    p = tmp_path / "p.json"
    save_project_schema(project, p)

    rt = AgentRuntime()
    resp = rt.execute(str(p), "summarize")
    rid = resp.run_manifest.get("runtime_id")
    artifact = tmp_path / ".luxera" / "agent_sessions" / f"{rid}.json"
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["runtime_id"] == rid
    assert payload["intent"] == "summarize"

