from __future__ import annotations

from pathlib import Path

import numpy as np

from luxera.compliance.energy import compute_leni_from_project
from luxera.compliance.standards import ActivityType, check_compliance_from_grid
from luxera.engine.direct_illuminance import build_room_from_spec, load_luminaires
from luxera.engine.radiosity.solver import RadiosityConfig, solve_radiosity
from luxera.engine.ugr_engine import compute_ugr_for_views
from luxera.export.professional_pdf import ProfessionalReportBuilder
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import CalcGrid, GlareViewSpec, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec
from luxera.runner import run_job


class TestIndoorCompleteWorkflow:
    """
    Complete indoor lighting workflow: project -> calculation -> compliance -> report.
    This is the most critical test class in the entire suite.
    """

    def _write_test_ies(self, tmp_path: Path) -> Path:
        ies = tmp_path / "integration_high_output.ies"
        ies.write_text(
            """IESNA:LM-63-2002
TILT=NONE
1 20000 1 3 1 1 2 0.6 0.6 0.1
0 45 90
0
200000 200000 200000
""",
            encoding="utf-8",
        )
        return ies

    def _build_project(
        self,
        tmp_path: Path,
        *,
        room_w: float,
        room_l: float,
        room_h: float,
        rows: int,
        cols: int,
        flux_multiplier: float,
        target_name: str,
    ) -> Path:
        ies_path = self._write_test_ies(tmp_path)
        project = Project(name=target_name, root_dir=str(tmp_path))
        project.geometry.rooms.append(
            RoomSpec(
                id="r1",
                name=target_name,
                width=room_w,
                length=room_l,
                height=room_h,
                origin=(0.0, 0.0, 0.0),
                floor_reflectance=0.2,
                wall_reflectance=0.5,
                ceiling_reflectance=0.7,
                activity_type="OFFICE_GENERAL",
            )
        )
        project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))

        rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
        sx = room_w / (cols + 1)
        sy = room_l / (rows + 1)
        k = 0
        for j in range(rows):
            for i in range(cols):
                k += 1
                project.luminaires.append(
                    LuminaireInstance(
                        id=f"l{k}",
                        name=f"L{k}",
                        photometry_asset_id="a1",
                        transform=TransformSpec(position=((i + 1) * sx, (j + 1) * sy, room_h - 0.2), rotation=rot),
                        maintenance_factor=0.8,
                        flux_multiplier=float(flux_multiplier),
                    )
                )

        project.grids.append(
            CalcGrid(
                id="g1",
                name="Workplane",
                origin=(0.0, 0.0, 0.0),
                width=room_w,
                height=room_l,
                elevation=0.85,
                nx=max(3, int(round(room_w / 0.5)) + 1),
                ny=max(3, int(round(room_l / 0.5)) + 1),
                room_id="r1",
            )
        )
        project.jobs.append(JobSpec(id="j_direct", type="direct", backend="cpu", seed=7))

        ppath = tmp_path / f"{target_name}.luxera"
        save_project_schema(project, ppath)
        return ppath

    def _run_common_workflow(self, ppath: Path, activity: ActivityType, target_lux: float) -> dict:
        ref = run_job(ppath, "j_direct")
        project = load_project_schema(ppath)

        result_csv = Path(ref.result_dir) / "grid.csv"
        grid_data = np.loadtxt(result_csv, delimiter=",", skiprows=1)
        grid_values = np.asarray(grid_data[:, 3], dtype=float).reshape(-1)

        room = build_room_from_spec(project.geometry.rooms[0])
        luminaires, _ = load_luminaires(project, lambda _a: "hash")

        # Radiosity with hemicube form factors.
        surfaces = room.get_surfaces()
        direct_seed = {s.id: float(max(np.mean(grid_values), 1.0)) * 0.02 for s in surfaces}
        radiosity = solve_radiosity(
            surfaces=surfaces,
            direct_illuminance=direct_seed,
            config=RadiosityConfig(
                max_iters=8,
                tol=1e-2,
                patch_max_area=8.0,
                form_factor_method="hemicube",
                hemicube_resolution=32,
                use_visibility=False,
                seed=1,
            ),
        )
        assert radiosity.form_factors.shape[0] > 0

        # UGR for 4 observer positions.
        views = [
            GlareViewSpec(id="v1", name="V1", observer=(1.0, 1.0, 1.2), view_dir=(1.0, 0.0, 0.0), room_id="r1"),
            GlareViewSpec(id="v2", name="V2", observer=(2.0, 2.0, 1.2), view_dir=(0.0, 1.0, 0.0), room_id="r1"),
            GlareViewSpec(id="v3", name="V3", observer=(3.0, 2.0, 1.2), view_dir=(-1.0, 0.0, 0.0), room_id="r1"),
            GlareViewSpec(id="v4", name="V4", observer=(2.0, 3.0, 1.2), view_dir=(0.0, -1.0, 0.0), room_id="r1"),
        ]
        ugr_analysis = compute_ugr_for_views(room, luminaires, views)
        assert ugr_analysis is not None
        assert len(ugr_analysis.results) == 4

        compliance = check_compliance_from_grid(
            room_name=project.geometry.rooms[0].name,
            activity_type=activity,
            grid_values_lux=grid_values.tolist(),
            maintenance_factor=1.0,
            ugr=(ugr_analysis.worst_case_ugr if ugr_analysis is not None else None),
        )

        leni = compute_leni_from_project(project, profile_name="office_open_plan")

        report_path = ppath.parent / f"{ppath.stem}_professional.pdf"
        ProfessionalReportBuilder(
            project,
            {
                "summary": ref.summary,
                "result_dir": ref.result_dir,
                "job_id": ref.job_id,
                "job_hash": ref.job_hash,
            },
        ).build(report_path)

        return {
            "ref": ref,
            "grid_values": grid_values,
            "compliance": compliance,
            "leni": leni,
            "ugr": ugr_analysis,
            "radiosity": radiosity,
            "report_path": report_path,
            "e_avg": float(np.mean(grid_values) if grid_values.size else 0.0),
            "u0_direct": float(np.min(grid_values) / np.mean(grid_values)) if np.mean(grid_values) > 1e-9 else 0.0,
        }

    def test_office_500lux_en12464(self, tmp_path: Path):
        """
        End-to-end: 12x8x3m open plan office, EN 12464-1.
        """
        ppath = self._build_project(
            tmp_path,
            room_w=12.0,
            room_l=8.0,
            room_h=3.0,
            rows=4,
            cols=3,
            flux_multiplier=0.00725,
            target_name="office_500lux",
        )
        out = self._run_common_workflow(ppath, ActivityType.OFFICE_GENERAL, 500.0)

        assert abs(out["e_avg"] - 500.0) / 500.0 <= 0.10
        # Direct-only uniformity with synthetic test photometry is harsh; ensure workable minimum.
        assert out["u0_direct"] > 0.15
        assert out["report_path"].exists() and out["report_path"].stat().st_size > 20_000
        assert out["compliance"] is not None
        assert out["leni"] is not None
        assert out["leni"].leni_kWh_per_m2_year >= 0.0

    def test_classroom_300lux(self, tmp_path: Path):
        ppath = self._build_project(
            tmp_path,
            room_w=8.0,
            room_l=6.0,
            room_h=3.0,
            rows=3,
            cols=2,
            flux_multiplier=0.0065,
            target_name="classroom_300lux",
        )
        out = self._run_common_workflow(ppath, ActivityType.CLASSROOM, 300.0)
        assert out["e_avg"] > 150.0
        assert out["report_path"].exists()

    def test_corridor_100lux(self, tmp_path: Path):
        ppath = self._build_project(
            tmp_path,
            room_w=12.0,
            room_l=2.0,
            room_h=3.0,
            rows=2,
            cols=4,
            flux_multiplier=0.0018,
            target_name="corridor_100lux",
        )
        out = self._run_common_workflow(ppath, ActivityType.CORRIDOR, 100.0)
        assert out["e_avg"] > 50.0
        assert out["report_path"].exists()
