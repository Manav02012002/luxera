from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from luxera.backends import radiance as rad
from luxera.project.runner import run_job_in_memory
from luxera.project.schema import JobSpec, LuminaireInstance, PhotometryAsset, Project, RoadwayGridSpec, RoadwaySpec, RotationSpec, TransformSpec

pytestmark = pytest.mark.radiance


def _ies_fixture(path: Path) -> Path:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
900 700 500
""",
        encoding="utf-8",
    )
    return path


def _seed_project(tmp_path: Path) -> Project:
    p = Project(name="road-radiance-v2", root_dir=str(tmp_path))
    ies = _ies_fixture(tmp_path / "fixture.ies")
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(15.0, 2.0, 8.0), rotation=rot),
        )
    )
    p.roadways.append(RoadwaySpec(id="rw1", name="Road", start=(0.0, 0.0, 0.0), end=(60.0, 0.0, 0.0), num_lanes=2, lane_width=3.5))
    p.roadway_grids.append(
        RoadwayGridSpec(
            id="rg1",
            name="Road Grid",
            lane_width=3.5,
            road_length=60.0,
            nx=12,
            ny=6,
            roadway_id="rw1",
            num_lanes=2,
            longitudinal_points=12,
            transverse_points_per_lane=3,
        )
    )
    p.jobs.append(JobSpec(id="j1", type="roadway", backend="radiance", settings={"road_class": "M3"}))
    return p


def test_roadway_luminance_radiance_backend_mocked(monkeypatch, tmp_path: Path) -> None:
    project = _seed_project(tmp_path)

    monkeypatch.setattr(rad.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    def fake_check_call(cmd, stdout=None, stderr=None):  # noqa: ARG001
        if stdout is not None:
            stdout.write(b"OCT")
        return 0

    def fake_check_output(cmd, stderr=None, text=False, input=None):  # noqa: ARG001
        if "-version" in cmd:
            return "rtrace 5.4a"
        n = 72  # 12 * 6 grid
        rgb = "\n".join(f"0 {((i % 12) + 1) / 100.0:.6f} 0" for i in range(n)).encode("utf-8")
        return rgb.decode("utf-8") if text else rgb

    monkeypatch.setattr(rad.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(rad.subprocess, "check_output", fake_check_output)

    ref = run_job_in_memory(project, "j1")
    summary = ref.summary
    assert "road_luminance_mean_cd_m2" in summary
    assert "lane_metrics" in summary
    lanes = summary.get("lane_metrics", [])
    assert isinstance(lanes, list) and lanes
    assert "luminance_mean_cd_m2" in lanes[0]

    result_dir = Path(ref.result_dir)
    assert (result_dir / "road_summary.json").exists()
    assert (result_dir / "road_grid_1.csv").exists()
    meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    assert meta.get("backend", {}).get("name") == "radiance"
