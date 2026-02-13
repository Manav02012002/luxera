from __future__ import annotations

import json
from pathlib import Path

from luxera.cli import main
from luxera.project.io import load_project_schema, save_project_schema
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
    VerticalPlaneSpec,
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


def test_indoor_multicalc_job_run_all_contract(tmp_path: Path) -> None:
    project_path = tmp_path / "indoor_multi.json"
    ies = _ies_fixture(tmp_path / "multi.ies")
    p = Project(name="Indoor Multi Calc", root_dir=str(tmp_path))
    p.geometry.rooms.append(RoomSpec(id="r1", name="Room 1", width=8.0, length=6.0, height=3.0))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Luminaire",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(4.0, 3.0, 2.8), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="Grid 1", origin=(0.0, 0.0, 0.0), width=8.0, height=6.0, elevation=0.8, nx=5, ny=4, room_id="r1"))
    p.grids.append(CalcGrid(id="g2", name="Grid 2", origin=(1.0, 1.0, 0.0), width=6.0, height=4.0, elevation=0.8, nx=4, ny=3, room_id="r1"))
    p.vertical_planes.append(
        VerticalPlaneSpec(
            id="vp1",
            name="VP 1",
            origin=(0.0, 0.0, 0.8),
            width=8.0,
            height=2.0,
            nx=6,
            ny=3,
            azimuth_deg=0.0,
            room_id="r1",
        )
    )
    p.point_sets.append(
        PointSetSpec(
            id="ps1",
            name="PS 1",
            points=[(0.5, 0.5, 0.8), (7.5, 5.5, 0.8)],
            room_id="r1",
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", settings={"use_occlusion": False}))
    save_project_schema(p, project_path)

    assert main(["run-all", str(project_path), "--job", "j1"]) == 0

    loaded = load_project_schema(project_path)
    ref = next((r for r in loaded.results if r.job_id == "j1"), None)
    assert ref is not None
    out_dir = Path(ref.result_dir)

    assert (out_dir / "grid_g1.csv").exists()
    assert (out_dir / "grid_g2.csv").exists()
    assert (out_dir / "grid_g1_heatmap.png").exists()
    assert (out_dir / "grid_g1_isolux.png").exists()
    assert (out_dir / "vplane_vp1.csv").exists()
    assert (out_dir / "vplane_vp1_heatmap.png").exists()
    assert (out_dir / "points_ps1.csv").exists()

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary.get("calc_object_count") == 4
    assert "global_worst_min_lux" in summary
    assert "global_worst_uniformity_ratio" in summary
    assert "global_highest_ugr" in summary
    calc_objects = summary.get("calc_objects")
    assert isinstance(calc_objects, list) and len(calc_objects) == 4
    for obj in calc_objects:
        assert isinstance(obj, dict)
        s = obj.get("summary", {})
        assert "min_lux" in s
        assert "mean_lux" in s
        assert "max_lux" in s
        assert "uniformity_ratio" in s
