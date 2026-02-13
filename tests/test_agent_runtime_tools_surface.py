from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from luxera.agent.runtime import AgentRuntime
from luxera.agent.tools.api import AgentTools, ToolResult
from luxera.project.diff import ProjectDiff
from luxera.project.io import save_project_schema
from luxera.project.schema import Project, RoomSpec, PhotometryAsset, LuminaireInstance, TransformSpec, RotationSpec, JobSpec, CalcGrid


@dataclass
class SpyTools(AgentTools):
    calls: List[str] = field(default_factory=list)

    def open_project(self, project_path: str):
        self.calls.append("open_project")
        return super().open_project(project_path)

    def save_project(self, project, project_path: Path):
        self.calls.append("save_project")
        return super().save_project(project, project_path)

    def propose_layout_diff(self, project, target_lux: float, constraints=None):
        self.calls.append("propose_layout_diff")
        return super().propose_layout_diff(project, target_lux, constraints=constraints)

    def apply_diff(self, project, diff, approved=False):
        self.calls.append("apply_diff")
        return super().apply_diff(project, diff, approved=approved)

    def run_job(self, project, job_id: str, approved=False):
        self.calls.append("run_job")
        return ToolResult(ok=False, requires_approval=not approved, message="blocked for test")

    def optimize_layout_search(self, project, job_id: str, constraints=None, max_rows=6, max_cols=6, top_n=8):
        self.calls.append("optimize_layout_search")
        return ToolResult(
            ok=True,
            message="ok",
            data={
                "best": {"rows": 2, "cols": 2, "score": 1.0},
                "top": [],
                "artifact_json": "",
                "diff": ProjectDiff(ops=[]),
            },
        )

    def optimize_layout_candidates(self, project, job_id: str, candidate_limit=12, constraints=None):
        self.calls.append("optimize_layout_candidates")
        return ToolResult(
            ok=True,
            message="ok",
            data={
                "candidates_csv": "candidates.csv",
                "topk_csv": "topk.csv",
                "best_diff_json": "best_diff.json",
                "optimizer_manifest_json": "optimizer_manifest.json",
            },
        )

    def summarize_project_context(self, project):
        self.calls.append("summarize_project_context")
        return ToolResult(ok=True, message="ok", data={"summary": {"project_name": project.name}})

    def propose_optimizations(self, project, job_id: str, constraints=None, top_n: int = 5):
        self.calls.append("propose_optimizations")
        return ToolResult(
            ok=True,
            message="ok",
            data={
                "job_id": job_id,
                "options": [
                    {"index": 0, "rows": 2, "cols": 2, "dimming": 1.0},
                    {"index": 1, "rows": 3, "cols": 2, "dimming": 0.8},
                ],
                "preview": {"ops": [], "count": 0},
            },
        )

    def optimization_option_diff(self, project, option):
        self.calls.append("optimization_option_diff")
        return ToolResult(ok=True, message="ok", data={"diff": ProjectDiff(ops=[]), "preview": {"ops": [], "count": 0}})


def _make(tmp_path: Path) -> Path:
    p = Project(name="Spy", root_dir=str(tmp_path))
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
    p.luminaires.append(LuminaireInstance(id="l1", name="L1", photometry_asset_id="a1", transform=TransformSpec(position=(1, 1, 2.8), rotation=rot)))
    p.grids.append(CalcGrid(id="g1", name="g", origin=(0, 0, 0), width=4, height=4, elevation=0.8, nx=3, ny=3))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    path = tmp_path / "p.json"
    save_project_schema(p, path)
    return path


def test_runtime_uses_tool_surface(tmp_path: Path):
    path = _make(tmp_path)
    tools = SpyTools()
    rt = AgentRuntime(tools=tools)
    rt.execute(str(path), "/place panels target 500 lux run")
    assert "open_project" in tools.calls
    assert "propose_layout_diff" in tools.calls
    assert "save_project" in tools.calls


def test_runtime_optimizer_uses_registry_tool(tmp_path: Path):
    path = _make(tmp_path)
    tools = SpyTools()
    rt = AgentRuntime(tools=tools)
    rt.execute(str(path), "optimize power")
    assert "optimize_layout_search" in tools.calls


def test_runtime_try_n_options_uses_optimizer_tool(tmp_path: Path):
    path = _make(tmp_path)
    tools = SpyTools()
    rt = AgentRuntime(tools=tools)
    rt.execute(str(path), "try 12 options")
    assert "optimize_layout_candidates" in tools.calls


def test_runtime_design_solve_uses_selected_option_diff(tmp_path: Path):
    path = _make(tmp_path)
    tools = SpyTools()
    rt = AgentRuntime(tools=tools)
    res = rt.execute(str(path), "design solve hit 500 lux and UGR < 19", approvals={"apply_diff": True, "selected_option_index": 1})
    assert "propose_optimizations" in tools.calls
    assert "optimization_option_diff" in tools.calls
    assert int(res.run_manifest.get("design_solve", {}).get("selected_option_index", -1)) == 1
