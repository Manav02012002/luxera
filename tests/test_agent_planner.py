from __future__ import annotations

import json
from pathlib import Path

from luxera.agent.planner import MockPlannerBackend
from luxera.agent.runtime import AgentRuntime
from luxera.agent.tools.api import AgentTools
from luxera.agent.tools.registry import build_default_registry
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def _make_project(tmp_path: Path) -> Path:
    p = Project(name="PlannerRt", root_dir=str(tmp_path))
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


def test_tool_schema_generation_snapshot() -> None:
    registry = build_default_registry(AgentTools())
    got = registry.json_schemas()
    snap_path = Path(__file__).parent / "snapshots" / "agent_tool_schemas.json"
    expected = json.loads(snap_path.read_text(encoding="utf-8"))
    assert got == expected


def test_mock_planner_executes_canned_multi_step_plan(tmp_path: Path) -> None:
    project_path = _make_project(tmp_path)
    planner = MockPlannerBackend(
        plans={
            "canned": {
                "calls": [
                    {"tool": "project.diff.propose_layout", "args": {"target_lux": 500.0, "constraints": {"max_rows": 6, "max_cols": 6}}},
                    {"tool": "project.diff.apply", "args": {"diff": "$latest_diff"}},
                    {"tool": "job.run", "args": {"job_id": "$first_job_id"}},
                ]
            }
        }
    )
    rt = AgentRuntime(planner=planner)
    res = rt.execute(str(project_path), "use canned plan", approvals={"apply_diff": True, "run_job": True})
    tools = [str(c.get("tool")) for c in res.session_log.tool_calls if isinstance(c, dict) and "tool" in c]
    assert tools[:3] == ["project.diff.propose_layout", "project.diff.apply", "job.run"]
    assert isinstance(res.run_manifest.get("step_logs"), list)
    assert isinstance(res.run_manifest.get("intermediate_results"), dict)
    assert any(str(p).endswith(".luxera/results") or "/results/" in str(p) for p in res.produced_artifacts)


def test_diff_and_approval_gate_enforced(tmp_path: Path) -> None:
    project_path = _make_project(tmp_path)
    planner = MockPlannerBackend(
        plans={
            "gated": {
                "calls": [
                    {"tool": "project.diff.propose_layout", "args": {"target_lux": 500.0, "constraints": {"max_rows": 6, "max_cols": 6}}},
                    {"tool": "project.diff.apply", "args": {"diff": "$latest_diff"}},
                    {"tool": "job.run", "args": {"job_id": "$first_job_id"}},
                ]
            }
        }
    )
    rt = AgentRuntime(planner=planner)
    res = rt.execute(str(project_path), "gated plan")
    kinds = [a.kind for a in res.actions]
    assert "apply_diff" in kinds
    assert "run_job" in kinds
    tools = [str(c.get("tool")) for c in res.session_log.tool_calls if isinstance(c, dict) and "tool" in c]
    assert "project.diff.apply" not in tools
    assert "job.run" not in tools
