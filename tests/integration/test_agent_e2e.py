from __future__ import annotations

from pathlib import Path

from luxera.agent.batch import BatchRunner, BatchStep
from luxera.agent.pipeline import CompliancePipeline
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.scenes import ControlGroup, LightScene, SceneManager
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec
from luxera.runner import run_job


def _write_test_ies(tmp_path: Path) -> Path:
    ies = tmp_path / "agent_fixture.ies"
    ies.write_text(
        """IESNA:LM-63-2002
TILT=NONE
1 12000 1 5 1 1 2 0.6 0.6 0.1
0 22.5 45 67.5 90
0
85000 70000 50000 22000 0
""",
        encoding="utf-8",
    )
    return ies


def _build_scene_project(tmp_path: Path) -> Path:
    p = Project(name="Scene Workflow", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="Office", width=6.0, length=4.0, height=3.0, activity_type="OFFICE_GENERAL"))

    ies = _write_test_ies(tmp_path)
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))

    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    positions = [(2.0, 1.5, 2.8), (4.0, 1.5, 2.8), (2.0, 2.8, 2.8), (4.0, 2.8, 2.8)]
    for i, pos in enumerate(positions, start=1):
        p.luminaires.append(
            LuminaireInstance(
                id=f"l{i}",
                name=f"L{i}",
                photometry_asset_id="a1",
                transform=TransformSpec(position=pos, rotation=rot),
                maintenance_factor=0.8,
                flux_multiplier=1.0,
            )
        )

    p.grids.append(CalcGrid(id="g1", name="WP", origin=(0.0, 0.0, 0.0), width=6.0, height=4.0, elevation=0.85, nx=13, ny=9, room_id="r1"))
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", seed=3))

    path = tmp_path / "scene_workflow.luxera"
    save_project_schema(p, path)
    return path


class TestAgentE2E:
    def test_autopilot_office(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "autopilot"
        pipe = CompliancePipeline(output_dir=out_dir, default_ies_path=_write_test_ies(tmp_path))

        result = pipe.run("500 lux open plan office 12x8m EN 12464")

        assert result.project_path.exists()
        assert result.report_path.exists()
        assert result.final_E_avg > 0.0

    def test_batch_three_steps(self, tmp_path: Path) -> None:
        project_path = _build_scene_project(tmp_path)
        runner = BatchRunner(project_path=str(project_path), output_dir=tmp_path / "batch_out")

        steps = [
            BatchStep(intent="create 6x4m room", fail_on_error=False),
            BatchStep(intent="run calculation", fail_on_error=False),
            BatchStep(intent="generate report", fail_on_error=False),
        ]
        results = runner.run_steps(steps)

        assert len(results) == 3
        assert all(r.success for r in results)

    def test_light_scenes_workflow(self, tmp_path: Path) -> None:
        project_path = _build_scene_project(tmp_path)
        project = load_project_schema(project_path)

        sm = SceneManager(project)
        sm.add_group(ControlGroup(id="g_perimeter", name="Perimeter", luminaire_ids=["l1", "l2"], default_dimming=1.0))
        sm.add_group(ControlGroup(id="g_core", name="Core", luminaire_ids=["l3", "l4"], default_dimming=1.0))

        sm.add_scene(LightScene(id="scene_full", name="Full", description="All on", dimming_overrides={"g_perimeter": 1.0, "g_core": 1.0}))
        sm.add_scene(LightScene(id="scene_dim", name="Dim", description="Core dimmed", dimming_overrides={"g_perimeter": 1.0, "g_core": 0.35}))

        p_full = sm.apply_scene_to_project("scene_full")
        p_dim = sm.apply_scene_to_project("scene_dim")

        path_full = tmp_path / "scene_full.luxera"
        path_dim = tmp_path / "scene_dim.luxera"
        save_project_schema(p_full, path_full)
        save_project_schema(p_dim, path_dim)

        r_full = run_job(path_full, "j1")
        r_dim = run_job(path_dim, "j1")

        e_full = float(r_full.summary.get("mean_lux", 0.0))
        e_dim = float(r_dim.summary.get("mean_lux", 0.0))
        assert e_full > 0.0
        assert e_dim > 0.0
        assert e_full != e_dim
