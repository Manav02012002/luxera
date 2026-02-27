from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def _seed_project(tmp_path: Path, *, with_extra_glare_source: bool = False) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = Project(name="road-glare", root_dir=str(tmp_path))
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
    if with_extra_glare_source:
        p.luminaires.append(
            LuminaireInstance(
                id="l2",
                name="L2",
                photometry_asset_id="a1",
                transform=TransformSpec(position=(-10.0, 1.75, 8.0), rotation=rot),
            )
        )
    p.roadways.append(RoadwaySpec(id="rw1", name="Road", start=(0.0, 0.0, 0.0), end=(30.0, 0.0, 0.0), num_lanes=2, lane_width=3.5))
    p.roadway_grids.append(
        RoadwayGridSpec(
            id="rg1",
            name="RG",
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
    p.jobs.append(
        JobSpec(
            id="j1",
            type="roadway",
            backend="cpu",
            settings={
                "road_surface_class": "R3",
                "glare_method": "rp8_veiling_ratio",
            },
        )
    )
    return p


def test_roadway_glare_monotonicity_extra_source_worsens_metric(tmp_path: Path) -> None:
    p_base = _seed_project(tmp_path / "base", with_extra_glare_source=False)
    p_worse = _seed_project(tmp_path / "worse", with_extra_glare_source=True)

    r_base = run_job_in_memory(p_base, "j1")
    r_worse = run_job_in_memory(p_worse, "j1")

    assert float(r_worse.summary["rp8_veiling_ratio_worst"]) > float(r_base.summary["rp8_veiling_ratio_worst"])
    assert float(r_worse.summary["threshold_increment_ti_proxy_percent"]) > float(r_base.summary["threshold_increment_ti_proxy_percent"])


def test_roadway_glare_golden_scene(tmp_path: Path) -> None:
    expected = json.loads(Path("tests/golden/roadway/glare_expected.json").read_text(encoding="utf-8"))
    tol = float(expected["tolerance_abs"])

    p = _seed_project(tmp_path / "golden", with_extra_glare_source=False)
    ref = run_job_in_memory(p, "j1")
    summary = ref.summary

    worst = summary.get("worst_case_glare", {})
    assert str(worst.get("method")) == str(expected["worst_case_glare"]["method"])
    assert float(worst.get("rp8_veiling_ratio_worst", 0.0)) == pytest.approx(float(expected["worst_case_glare"]["rp8_veiling_ratio_worst"]), abs=tol)
    assert float(worst.get("ti_proxy_percent_worst", 0.0)) == pytest.approx(float(expected["worst_case_glare"]["ti_proxy_percent_worst"]), abs=tol)
    assert float(worst.get("veiling_luminance_total_worst_cd_m2", 0.0)) == pytest.approx(
        float(expected["worst_case_glare"]["veiling_luminance_total_worst_cd_m2"]), abs=tol
    )

    rows = summary.get("observer_glare_views", [])
    by_id = {str(r.get("observer_id")): r for r in rows if isinstance(r, dict)}
    for er in expected.get("observer_rows", []):
        rr = by_id[str(er["observer_id"])]
        assert float(rr.get("rp8_veiling_ratio", 0.0)) == pytest.approx(float(er["rp8_veiling_ratio"]), abs=tol)
        assert float(rr.get("ti_proxy_percent", 0.0)) == pytest.approx(float(er["ti_proxy_percent"]), abs=tol)
        assert float(rr.get("veiling_luminance_total_cd_m2", 0.0)) == pytest.approx(float(er["veiling_luminance_total_cd_m2"]), abs=tol)
