from __future__ import annotations

import json
from pathlib import Path

from luxera.agent.context import context_memory_path, load_context_memory
from luxera.agent.planner import PlannerBackend, PlannerOutput
from luxera.agent.runtime import AgentRuntime
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def _make_project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = Project(name="CtxMem", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="R", width=6, length=8, height=3))
    ies = tmp_path / "a.ies"
    ies.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(1, 1, 2.8), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="g", origin=(0, 0, 0), width=4, height=4, elevation=0.8, nx=3, ny=3, room_id="r1"))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    path = tmp_path / "p.json"
    save_project_schema(p, path)
    return path


def test_context_updates_after_tool_actions(tmp_path: Path) -> None:
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    rt.execute(str(project_path), "/grid 0.8 0.5")

    mem_path = context_memory_path(project_path)
    assert mem_path.exists()
    memory = load_context_memory(project_path).to_dict()
    assert memory["turn_count"] == 1
    rolling = memory["rolling_summary"]
    assert int(rolling["geometry"]["grid_count"]) >= 2
    assert "project.grid.add" in rolling["last_actions"]


class _CapturePlanner(PlannerBackend):
    def __init__(self) -> None:
        self.last_context = None

    def plan(self, *, intent: str, project_context, tool_schemas) -> PlannerOutput:
        self.last_context = dict(project_context)
        return PlannerOutput(calls=[], rationale="capture")


def test_context_injected_into_planner_calls(tmp_path: Path) -> None:
    project_path = _make_project(tmp_path)
    planner = _CapturePlanner()
    rt = AgentRuntime(planner=planner)
    rt.execute(str(project_path), "summarize")
    assert isinstance(planner.last_context, dict)
    assert "agent_memory" in planner.last_context
    assert planner.last_context["agent_memory"]["schema_version"] == 1


def test_context_memory_determinism_across_runs(tmp_path: Path) -> None:
    p1 = _make_project(tmp_path / "a")
    p2 = _make_project(tmp_path / "b")
    rt1 = AgentRuntime()
    rt2 = AgentRuntime()
    rt1.execute(str(p1), "/grid 0.8 0.5")
    rt2.execute(str(p2), "/grid 0.8 0.5")
    m1 = json.loads(context_memory_path(p1).read_text(encoding="utf-8"))
    m2 = json.loads(context_memory_path(p2).read_text(encoding="utf-8"))
    assert m1 == m2
