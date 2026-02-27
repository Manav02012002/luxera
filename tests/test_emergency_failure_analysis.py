from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from luxera.project.schema import (
    CalcGrid,
    EmergencyModeSpec,
    EmergencySpec,
    EscapeRouteSpec,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RotationSpec,
    TransformSpec,
)
from luxera.runner import run_job_in_memory as run_job


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


def _seed_project(tmp_path: Path) -> Project:
    tmp_path.mkdir(parents=True, exist_ok=True)
    ies = _ies_fixture(tmp_path / "f.ies")
    p = Project(name="EmergencyFailure", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.extend(
        [
            LuminaireInstance(
                id="l1",
                name="L1",
                photometry_asset_id="a1",
                transform=TransformSpec(position=(0.5, 2.2, 3.2), rotation=rot),
                emergency_operation="maintained",
                emergency_output_factor=1.0,
            ),
            LuminaireInstance(
                id="l2",
                name="L2",
                photometry_asset_id="a1",
                transform=TransformSpec(position=(5.0, 1.0, 2.2), rotation=rot),
                emergency_operation="maintained",
                emergency_output_factor=1.0,
            ),
            LuminaireInstance(
                id="l3",
                name="L3",
                photometry_asset_id="a1",
                transform=TransformSpec(position=(9.5, 2.2, 3.2), rotation=rot),
                emergency_operation="non_maintained",
                emergency_output_factor=1.0,
            ),
        ]
    )
    p.grids.append(CalcGrid(id="g1", name="open", origin=(0.0, 0.0, 0.0), width=10.0, height=2.0, elevation=0.0, nx=11, ny=3))
    p.escape_routes.append(EscapeRouteSpec(id="r1", name="r1", polyline=[(0.0, 1.0, 0.0), (10.0, 1.0, 0.0)], width_m=1.0, spacing_m=0.5))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="emergency",
            emergency=EmergencySpec(standard="EN1838", route_min_lux=0.1, route_u0_min=0.01, open_area_min_lux=0.1, open_area_u0_min=0.01),
            mode=EmergencyModeSpec(emergency_factor=1.0, battery_output_factor=0.8),
            routes=["r1"],
            open_area_targets=["g1"],
        )
    )
    return p


def test_closest_luminaire_failure_is_worst_for_route_min(tmp_path: Path) -> None:
    p = _seed_project(tmp_path / "closest")
    ref = run_job(p, "j1")
    summary = ref.summary
    worst = summary.get("worst_single_failure", {})
    assert str(worst.get("route_id")) == "r1"
    assert float(worst.get("drop_lux", 0.0)) > 0.0
    route_rows = summary.get("route_results", [])
    assert isinstance(route_rows, list) and route_rows
    # In this known tiny scene, minimum route illuminance occurs near route start.
    # The nearest luminaire to that critical location should have the largest failure impact.
    critical_point = np.asarray([0.0, 1.0, 0.0], dtype=float)
    by_dist = []
    for lum in p.luminaires:
        pos = np.asarray(lum.transform.position, dtype=float)
        d = float(np.linalg.norm(critical_point - pos))
        by_dist.append((d, lum.id))
    by_dist.sort(key=lambda x: (x[0], x[1]))
    assert str(worst.get("luminaire_id")) == by_dist[0][1]


def test_failure_ranking_is_deterministic(tmp_path: Path) -> None:
    p1 = _seed_project(tmp_path / "a")
    p2 = _seed_project(tmp_path / "b")
    r1 = run_job(p1, "j1")
    r2 = run_job(p2, "j1")
    a = r1.summary.get("route_failure_analysis", [])
    b = r2.summary.get("route_failure_analysis", [])
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert r1.summary.get("luminaire_operation_counts", {}) == {"maintained": 2, "non_maintained": 1, "none": 0}
