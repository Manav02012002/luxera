from pathlib import Path

from luxera.export.roadway_report import render_roadway_report_html
from luxera.project.schema import (
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoadwayGridSpec,
    RotationSpec,
    TransformSpec,
)
from luxera.runner import run_job_in_memory as run_job


def _ies(path: Path) -> Path:
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


def test_render_roadway_report_html(tmp_path: Path):
    ies = _ies(tmp_path / "road.ies")
    p = Project(name="RoadRep", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(10.0, 2.0, 8.0), rotation=rot),
        )
    )
    p.roadway_grids.append(RoadwayGridSpec(id="rg1", name="R1", lane_width=4.0, road_length=20.0, nx=10, ny=3))
    p.jobs.append(JobSpec(id="j1", type="roadway", settings={"road_class": "M3"}))

    ref = run_job(p, "j1")
    out = render_roadway_report_html(Path(ref.result_dir), tmp_path / "roadway.html")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Roadway Lighting Report" in text
    assert "observer_luminance_views" not in text  # rendered as table, not raw dict key
    assert "observer_luminance_max_cd_m2" in text
    assert "threshold_increment_ti_proxy_percent" in text
    assert "surround_ratio_proxy" in text
    assert "Roadway heatmap" in text or "Roadway isolux" in text
