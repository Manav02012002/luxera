from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from luxera.engine.road_reflection import lookup_reflection_coefficient
from luxera.project.runner import run_job_in_memory
from luxera.project.schema import (
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoadwayGridSpec,
    RoadwaySpec,
    RotationSpec,
    TransformSpec,
)


def _ies_fixture(path: Path) -> Path:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1200 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
900 700 500
""",
        encoding="utf-8",
    )
    return path


def _seed_project(tmp_path: Path, *, surface_class: str) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = Project(name=f"road-lum-{surface_class}", root_dir=str(tmp_path))
    ies = _ies_fixture(tmp_path / "fixture.ies")
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(12.0, 2.0, 8.0), rotation=rot),
        )
    )
    p.roadways.append(RoadwaySpec(id="rw1", name="Road", start=(0.0, 0.0, 0.0), end=(30.0, 0.0, 0.0), num_lanes=2, lane_width=3.5))
    p.roadway_grids.append(
        RoadwayGridSpec(
            id="rg1",
            name="Road Grid",
            lane_width=3.5,
            road_length=30.0,
            nx=6,
            ny=4,
            roadway_id="rw1",
            num_lanes=2,
            longitudinal_points=6,
            transverse_points_per_lane=2,
        )
    )
    p.jobs.append(JobSpec(id="j1", type="roadway", backend="cpu", settings={"road_class": "M3", "road_surface_class": surface_class}))
    return p


def test_reflection_table_bilinear_interpolation() -> None:
    v00 = lookup_reflection_coefficient("R3", beta_deg=0.0, tan_gamma=0.0).value
    v11 = lookup_reflection_coefficient("R3", beta_deg=15.0, tan_gamma=0.5).value
    mid = lookup_reflection_coefficient("R3", beta_deg=7.5, tan_gamma=0.25).value
    assert mid == pytest.approx((v00 + v11) * 0.5, rel=1e-6, abs=1e-9)


def test_surface_class_changes_luminance(tmp_path: Path) -> None:
    p_bright = _seed_project(tmp_path / "bright", surface_class="R1")
    p_dark = _seed_project(tmp_path / "dark", surface_class="R4")

    r_bright = run_job_in_memory(p_bright, "j1")
    r_dark = run_job_in_memory(p_dark, "j1")

    assert float(r_bright.summary["road_luminance_mean_cd_m2"]) > float(r_dark.summary["road_luminance_mean_cd_m2"])


def test_golden_roadway_luminance_points(tmp_path: Path) -> None:
    expected = json.loads(Path("tests/golden/roadway/luminance_points_expected.json").read_text(encoding="utf-8"))
    p = _seed_project(tmp_path, surface_class=str(expected["surface_class"]))
    ref = run_job_in_memory(p, "j1")

    out = json.loads((Path(ref.result_dir) / "results.json").read_text(encoding="utf-8"))
    tol = float(expected["tolerance_abs"])

    assert float(ref.summary["road_luminance_mean_cd_m2"]) == pytest.approx(
        float(expected["summary"]["road_luminance_mean_cd_m2"]), abs=tol
    )

    by_lane = {int(l["lane_number"]): l for l in out.get("lane_grids", [])}
    for row in expected.get("points", []):
        lane_num = int(row["lane_number"])
        order = int(row["order"])
        lane = by_lane[lane_num]
        pts = lane.get("points", [])
        match = next((p for p in pts if int(float(p.get("order", -1))) == order), None)
        assert match is not None
        assert float(match["x"]) == pytest.approx(float(row["x"]), abs=tol)
        assert float(match["y"]) == pytest.approx(float(row["y"]), abs=tol)
        assert float(match["luminance_cd_m2"]) == pytest.approx(float(row["luminance_cd_m2"]), abs=tol)


def test_roadway_luminance_is_deterministic_across_runs(tmp_path: Path) -> None:
    p1 = _seed_project(tmp_path / "run1", surface_class="R3")
    p2 = _seed_project(tmp_path / "run2", surface_class="R3")

    r1 = run_job_in_memory(p1, "j1")
    r2 = run_job_in_memory(p2, "j1")

    assert float(r1.summary["road_luminance_mean_cd_m2"]) == pytest.approx(float(r2.summary["road_luminance_mean_cd_m2"]), abs=1e-12)
    assert float(r1.summary["ul_longitudinal"]) == pytest.approx(float(r2.summary["ul_longitudinal"]), abs=1e-12)

    out1 = json.loads((Path(r1.result_dir) / "results.json").read_text(encoding="utf-8"))
    out2 = json.loads((Path(r2.result_dir) / "results.json").read_text(encoding="utf-8"))

    lanes1 = sorted(out1.get("lane_grids", []), key=lambda x: int(x.get("lane_number", 0)))
    lanes2 = sorted(out2.get("lane_grids", []), key=lambda x: int(x.get("lane_number", 0)))
    assert len(lanes1) == len(lanes2)
    for a, b in zip(lanes1, lanes2):
        pa = sorted(a.get("points", []), key=lambda r: int(float(r.get("order", 0.0))))
        pb = sorted(b.get("points", []), key=lambda r: int(float(r.get("order", 0.0))))
        assert len(pa) == len(pb)
        la = np.asarray([float(r.get("luminance_cd_m2", 0.0)) for r in pa], dtype=float)
        lb = np.asarray([float(r.get("luminance_cd_m2", 0.0)) for r in pb], dtype=float)
        assert np.allclose(la, lb, atol=1e-12, rtol=0.0)


def test_symmetric_layout_yields_symmetric_lane_luminance(tmp_path: Path) -> None:
    p = _seed_project(tmp_path / "sym", surface_class="R3")
    p.luminaires.clear()
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.extend(
        [
            LuminaireInstance(
                id="l1",
                name="L1",
                photometry_asset_id="a1",
                transform=TransformSpec(position=(12.0, 1.75, 8.0), rotation=rot),
            ),
            LuminaireInstance(
                id="l2",
                name="L2",
                photometry_asset_id="a1",
                transform=TransformSpec(position=(12.0, 5.25, 8.0), rotation=rot),
            ),
        ]
    )
    ref = run_job_in_memory(p, "j1")
    lane_metrics = sorted(ref.summary.get("lane_metrics", []), key=lambda x: int(float(x.get("lane_number", 0.0))))
    assert len(lane_metrics) >= 2
    l1 = lane_metrics[0]
    l2 = lane_metrics[1]
    assert float(l1["Lavg_cd_m2"]) == pytest.approx(float(l2["Lavg_cd_m2"]), rel=2e-3, abs=0.0)
    assert float(l1["Uo_luminance"]) == pytest.approx(float(l2["Uo_luminance"]), rel=2e-2, abs=0.0)
