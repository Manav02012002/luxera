from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from luxera.engine.road_illuminance import compute_lane_luminance_metrics
from luxera.project.io import load_project_schema
from luxera.project.runner import run_job_in_memory


def test_compute_lane_luminance_metrics_on_synthetic_grid() -> None:
    lum = np.array(
        [
            [1.0, 2.0, 4.0],
            [1.0, 2.0, 4.0],
            [2.0, 2.0, 2.0],
            [3.0, 3.0, 3.0],
        ],
        dtype=float,
    )
    lanes, worst = compute_lane_luminance_metrics(
        lum,
        lane_ranges=[(1, 0, 2), (2, 2, 4)],
        longitudinal_line_policy="center",
    )

    assert len(lanes) == 2
    l1, l2 = lanes
    assert l1["Lavg_cd_m2"] == pytest.approx(14.0 / 6.0)
    assert l1["Uo_luminance"] == pytest.approx(1.0 / (14.0 / 6.0))
    assert l1["Ul_luminance"] == pytest.approx(1.0 / 4.0)

    assert l2["Lavg_cd_m2"] == pytest.approx(2.5)
    assert l2["Uo_luminance"] == pytest.approx(2.0 / 2.5)
    assert l2["Ul_luminance"] == pytest.approx(1.0)

    assert worst["lavg_min_cd_m2"] == pytest.approx(l1["Lavg_cd_m2"])
    assert worst["uo_min"] == pytest.approx(l1["Uo_luminance"])
    assert worst["ul_min"] == pytest.approx(l1["Ul_luminance"])


def test_roadway_metrics_golden_scene_and_lane_luminance_csv(tmp_path: Path) -> None:
    expected = json.loads(Path("tests/golden/roadway/metrics_sample_expected.json").read_text(encoding="utf-8"))
    src = Path(str(expected["scene"])).resolve()
    dst = tmp_path / "roadway_basic"
    shutil.copytree(src.parent, dst)

    project_path = dst / src.name
    project = load_project_schema(project_path)
    project.root_dir = str(project_path.parent)
    ref = run_job_in_memory(project, str(expected["job_id"]))
    tol = float(expected["tolerance_abs"])

    summary = ref.summary
    worst = summary.get("roadway_worst_case", {})
    assert float(worst.get("lavg_min_cd_m2", 0.0)) == pytest.approx(float(expected["worst_case"]["lavg_min_cd_m2"]), abs=tol)
    assert float(worst.get("uo_min", 0.0)) == pytest.approx(float(expected["worst_case"]["uo_min"]), abs=tol)
    assert float(worst.get("ul_min", 0.0)) == pytest.approx(float(expected["worst_case"]["ul_min"]), abs=tol)

    by_lane = {int(float(l.get("lane_number", 0.0))): l for l in summary.get("lane_metrics", [])}
    for row in expected.get("lanes", []):
        lane = by_lane[int(row["lane_number"])]
        assert float(lane["Lavg_cd_m2"]) == pytest.approx(float(row["Lavg_cd_m2"]), abs=tol)
        assert float(lane["Uo_luminance"]) == pytest.approx(float(row["Uo_luminance"]), abs=tol)
        assert float(lane["Ul_luminance"]) == pytest.approx(float(row["Ul_luminance"]), abs=tol)

    result_dir = Path(ref.result_dir)
    assert (result_dir / "road_luminance_grid_1.csv").exists()
    assert (result_dir / "road_luminance_grid_2.csv").exists()
