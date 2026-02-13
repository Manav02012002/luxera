from __future__ import annotations

import json
from pathlib import Path

from luxera.project.runner import run_job_in_memory
from luxera.project.schema import (
    CalcGrid,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    PointSetSpec,
    Project,
    RoomSpec,
    RotationSpec,
    TransformSpec,
)


def _ies_fixture(path: Path) -> Path:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 700 300
""",
        encoding="utf-8",
    )
    return path


def test_indoor_multigrid_artifact_contract(tmp_path: Path):
    ies = _ies_fixture(tmp_path / "multi.ies")
    p = Project(name="Indoor Multi", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Lum",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 3.0), rotation=rot),
        )
    )
    p.geometry.rooms.append(RoomSpec(id="r1", name="Room", width=4.0, length=4.0, height=3.0))
    p.grids.append(CalcGrid(id="g1", name="Grid 1", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=4, ny=4, room_id="r1"))
    p.grids.append(CalcGrid(id="g2", name="Grid 2", origin=(0.5, 0.5, 0.0), width=3.0, height=3.0, elevation=0.8, nx=3, ny=3, room_id="r1"))
    p.point_sets.append(
        PointSetSpec(
            id="ps1",
            name="Points",
            points=[(1.0, 1.0, 0.8), (3.0, 3.0, 0.8)],
            room_id="r1",
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", settings={"use_occlusion": False}))

    ref = run_job_in_memory(p, "j1")
    out_dir = Path(ref.result_dir)

    assert (out_dir / "grid_g1.csv").exists()
    assert (out_dir / "grid_g2.csv").exists()
    assert (out_dir / "grid_g1_heatmap.png").exists()
    assert (out_dir / "grid_g2_heatmap.png").exists()
    assert (out_dir / "points_ps1.csv").exists()
    assert (out_dir / "summary.json").exists()

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = set((manifest.get("entries") or {}).keys())
    assert "grid_g1.csv" in entries
    assert "grid_g2.csv" in entries
    assert "points_ps1.csv" in entries
    assert "summary.json" in entries
