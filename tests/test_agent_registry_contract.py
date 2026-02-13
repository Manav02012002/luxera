import inspect
from pathlib import Path

from luxera.agent.runtime import AgentRuntime
from luxera.agent.tools.registry import build_default_registry
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
from luxera.project.schema import Project, JobSpec


def _seed_project(tmp_path: Path) -> Path:
    p = Project(name="Reg", root_dir=str(tmp_path))
    p.jobs.append(JobSpec(id="j1", type="daylight"))
    project_path = tmp_path / "p.json"
    save_project_schema(p, project_path)
    return project_path


def test_registry_has_permission_tags() -> None:
    reg = build_default_registry(AgentTools())
    desc = reg.describe()
    assert "project.open" in desc
    assert desc["project.open"]["permission_tag"] == "project_edit"
    assert desc["job.run"]["permission_tag"] == "run_job"
    assert desc["bundle.audit"]["permission_tag"] == "export"
    assert "create_room" in desc
    assert "run_calc" in desc
    assert "propose_optimizations" in desc


def test_runtime_structured_objects_always_present(tmp_path: Path) -> None:
    project_path = _seed_project(tmp_path)
    rt = AgentRuntime()
    resp = rt.execute(str(project_path), "cannot proceed needs input")
    assert resp.structured_plan is not None
    assert resp.structured_diff is not None
    assert resp.structured_manifest is not None
    assert resp.session_log is not None


def test_runtime_file_writes_only_within_tool_calls(tmp_path: Path, monkeypatch) -> None:
    project_path = _seed_project(tmp_path)
    rt = AgentRuntime()
    original_write_text = Path.write_text
    original_read_text = Path.read_text

    def guarded_write(self, *args, **kwargs):
        stack = inspect.stack()
        in_runtime = any("luxera/agent/runtime.py" in fr.filename for fr in stack)
        if in_runtime:
            assert rt._tool_call_depth > 0
        return original_write_text(self, *args, **kwargs)

    def guarded_read(self, *args, **kwargs):
        stack = inspect.stack()
        in_runtime = any("luxera/agent/runtime.py" in fr.filename for fr in stack)
        if in_runtime:
            assert rt._tool_call_depth > 0
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write)
    monkeypatch.setattr(Path, "read_text", guarded_read)
    rt.execute(str(project_path), "run")
