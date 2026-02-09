from pathlib import Path

from luxera.agent.runtime import AgentRuntime
from luxera.agent.tools.api import AgentTools
from luxera.project.io import save_project_schema
from luxera.project.schema import (
    CalcGrid,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoomSpec,
    RotationSpec,
    TransformSpec,
)


def _make_project(tmp_path: Path) -> Path:
    p = Project(name="AgentToolsExt", root_dir=str(tmp_path))
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


def test_agent_tools_assets_and_reports(tmp_path: Path):
    project_path = _make_project(tmp_path)
    tools = AgentTools()
    project, path = tools.open_project(str(project_path))

    add = tools.add_asset(project, str(tmp_path / "a.ies"), asset_id="a2")
    assert add.ok
    inspect = tools.inspect_asset(project, "a2")
    assert inspect.ok and inspect.data["format"] == "IES"
    hashed = tools.hash_asset(project, "a2")
    assert hashed.ok and hashed.data["hash"]

    run = tools.run_job(project, "j1", approved=True)
    assert run.ok

    heat = tools.render_heatmap(project, "j1")
    assert heat.ok
    assert "heatmap" in heat.data["artifacts"]

    pdf = tools.build_pdf(project, "j1", "en12464", str(tmp_path / "r.pdf"))
    assert pdf.ok
    assert Path(pdf.data["path"]).exists()

    tools.save_project(project, path)


def test_runtime_report_client_after_run(tmp_path: Path):
    project_path = _make_project(tmp_path)
    rt = AgentRuntime()
    rt.execute(str(project_path), "run", approvals={"run_job": True})
    res = rt.execute(str(project_path), "/report client")
    assert any(str(p).endswith(".zip") for p in res.produced_artifacts)
