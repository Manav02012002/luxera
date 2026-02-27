from __future__ import annotations

from pathlib import Path

from luxera.cli import main
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def _seed_small_office(tmp_path: Path) -> Path:
    p = Project(name="SmallOfficeBatch", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="Office", width=6.0, length=8.0, height=3.0))
    ies = tmp_path / "fixture.ies"
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
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="Workplane", origin=(0.5, 0.5, 0.0), width=5.0, height=7.0, elevation=0.8, nx=5, ny=7, room_id="r1"))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    path = tmp_path / "office.json"
    save_project_schema(p, path)
    return path


def test_cli_agent_batch_e2e_small_office(tmp_path: Path) -> None:
    project_path = _seed_small_office(tmp_path)
    out_dir = tmp_path / "out"
    rc = main(["agent", "run", "--project", str(project_path), "--approve-all", "--out", str(out_dir)])
    assert rc == 0
    assert (out_dir / "report.pdf").exists()
    assert (out_dir / "report.pdf").stat().st_size > 0
    assert (out_dir / "audit_bundle.zip").exists()
    assert (out_dir / "audit_bundle.zip").stat().st_size > 0
