from __future__ import annotations

import math
from pathlib import Path

import pytest

from luxera.project.runner import run_job_in_memory
from luxera.project.schema import (
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoadwayGridSpec,
    RoadwaySegmentSpec,
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


def _seed_project(tmp_path: Path, *, curve: bool = False, bank_deg: float = 0.0, flux_multiplier: float = 1.0, glare_method: str = "rp8_veiling_ratio") -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = Project(name="road-edge", root_dir=str(tmp_path))
    ies = _ies_fixture(tmp_path / "fixture.ies")
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            flux_multiplier=float(flux_multiplier),
            transform=TransformSpec(position=(12.0, 2.0, 8.0), rotation=rot),
        )
    )
    segment = None
    if curve or abs(float(bank_deg)) > 1e-9:
        segment = RoadwaySegmentSpec(
            length_m=40.0,
            lane_count=2,
            lane_widths_m=[3.5, 3.5],
            curve_radius_m=55.0 if curve else None,
            curve_angle_deg=35.0 if curve else None,
            curve_direction="left",
            bank_angle_deg=float(bank_deg),
        )
    p.roadways.append(
        RoadwaySpec(
            id="rw1",
            name="Road",
            start=(0.0, 0.0, 0.0),
            end=(40.0, 0.0, 0.0),
            num_lanes=2,
            lane_width=3.5,
            segment=segment,
        )
    )
    p.roadway_grids.append(
        RoadwayGridSpec(
            id="rg1",
            name="RG",
            lane_width=3.5,
            road_length=40.0,
            nx=8,
            ny=4,
            roadway_id="rw1",
            num_lanes=2,
            longitudinal_points=8,
            transverse_points_per_lane=2,
            observer_method="en13201_m",
        )
    )
    p.jobs.append(
        JobSpec(
            id="j1",
            type="roadway",
            backend="cpu",
            settings={"road_surface_class": "R3", "glare_method": glare_method},
        )
    )
    return p


def test_curve_longitudinal_spacing_is_uniform_along_arc(tmp_path: Path) -> None:
    p = _seed_project(tmp_path / "curve_spacing", curve=True, bank_deg=0.0)
    ref = run_job_in_memory(p, "j1")
    lane = sorted(ref.summary.get("roadway", {}).get("lanes", []), key=lambda x: int(x.get("lane_number", 0)))[0]
    pts = [r for r in lane.get("luminance_grid", []) if int(float(r.get("lane_row", -1))) == 0]
    pts = sorted(pts, key=lambda r: int(float(r.get("lane_col", 0.0))))
    assert len(pts) >= 4
    dists = []
    for i in range(1, len(pts)):
        x0, y0, z0 = float(pts[i - 1]["x"]), float(pts[i - 1]["y"]), float(pts[i - 1]["z"])
        x1, y1, z1 = float(pts[i]["x"]), float(pts[i]["y"]), float(pts[i]["z"])
        dists.append(math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2))
    assert max(dists) - min(dists) <= 1e-6


def test_banking_changes_point_plane_elevation(tmp_path: Path) -> None:
    bank_deg = 8.0
    p = _seed_project(tmp_path / "bank", curve=False, bank_deg=bank_deg)
    ref = run_job_in_memory(p, "j1")
    lane = sorted(ref.summary.get("roadway", {}).get("lanes", []), key=lambda x: int(x.get("lane_number", 0)))[0]
    pts = [r for r in lane.get("luminance_grid", []) if int(float(r.get("lane_col", -1))) == 0]
    pts = sorted(pts, key=lambda r: int(float(r.get("lane_row", 0.0))))
    assert len(pts) >= 2
    p0 = pts[0]
    p1 = pts[-1]
    dy = float(p1["y"]) - float(p0["y"])
    dz = float(p1["z"]) - float(p0["z"])
    assert dz > 0.0
    assert dz == pytest.approx(dy * math.tan(math.radians(bank_deg)), rel=0.0, abs=1e-6)


def test_ti_increases_with_higher_flux(tmp_path: Path) -> None:
    p_low = _seed_project(tmp_path / "ti_low", flux_multiplier=0.5, glare_method="ti_cie")
    p_high = _seed_project(tmp_path / "ti_high", flux_multiplier=1.5, glare_method="ti_cie")
    r_low = run_job_in_memory(p_low, "j1")
    r_high = run_job_in_memory(p_high, "j1")
    assert float(r_high.summary["threshold_increment_ti_percent"]) > float(r_low.summary["threshold_increment_ti_percent"])
