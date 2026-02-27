from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from luxera.engine.roadway_grids import build_lane_grid_payload, resolve_lane_slices, resolve_observers
from luxera.project.runner import run_job_in_memory
from luxera.project.schema import (
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoadwayGridSpec,
    RoadwayObserverSpec,
    RoadwayPoleRowSpec,
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


def _seed_project(tmp_path: Path) -> Project:
    project = Project(name="road-grid-determinism", root_dir=str(tmp_path))
    ies = _ies_fixture(tmp_path / "fixture.ies")
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(15.0, 2.0, 8.0), rotation=rot),
        )
    )
    project.roadways.append(
        RoadwaySpec(
            id="rw1",
            name="Road",
            start=(0.0, 0.0, 0.0),
            end=(40.0, 0.0, 0.0),
            num_lanes=2,
            lane_width=3.5,
            segment=RoadwaySegmentSpec(length_m=40.0, lane_count=2, lane_widths_m=[3.25, 3.75], lateral_offset_m=0.2),
            pole_rows=[RoadwayPoleRowSpec(id="row_a", spacing_m=30.0, offset_m=1.0, mounting_height_m=8.0)],
            observers=[
                RoadwayObserverSpec(id="obs_l1", lane_number=1, method="luminance", back_offset_m=50.0),
                RoadwayObserverSpec(id="obs_ti_2", lane_number=2, method="ti", back_offset_m=50.0),
            ],
        )
    )
    project.roadway_grids.append(
        RoadwayGridSpec(
            id="rg1",
            name="Road Grid",
            lane_width=3.5,
            road_length=40.0,
            nx=8,
            ny=6,
            roadway_id="rw1",
            num_lanes=2,
            longitudinal_points=8,
            transverse_points_per_lane=3,
            observer_method="en13201",
        )
    )
    project.jobs.append(JobSpec(id="j1", type="roadway", backend="cpu", settings={"road_class": "M3"}))
    return project


def test_lane_slices_and_point_ordering_are_deterministic() -> None:
    nx, ny = 4, 3
    points = np.array([[x, y, 0.0] for y in range(ny) for x in range(nx)], dtype=float)
    values = np.array([10.0 + i for i in range(nx * ny)], dtype=float)
    lane_widths = [3.0, 3.0]

    slices = resolve_lane_slices(num_lanes=2, ny=ny)
    assert [(s.y0, s.y1) for s in slices] == [(0, 2), (2, 3)]

    payload = build_lane_grid_payload(points, values, nx=nx, ny=ny, lane_widths=lane_widths)
    assert len(payload) == 2

    lane_1 = payload[0]
    lane_2 = payload[1]
    assert len(lane_1["points"]) == 8
    assert len(lane_2["points"]) == 4

    first = lane_1["points"][0]
    last = lane_1["points"][-1]
    assert first["order"] == 0.0
    assert first["x"] == 0.0
    assert first["y"] == 0.0
    assert first["illuminance_lux"] == 10.0
    assert last["lane_row"] == 1.0
    assert last["lane_col"] == 3.0


def test_observer_resolution_prefers_explicit_per_lane_definitions() -> None:
    roadway = RoadwaySpec(
        id="rw",
        name="Road",
        start=(0.0, 0.0, 0.0),
        end=(10.0, 0.0, 0.0),
        num_lanes=2,
        lane_width=3.5,
        observers=[
            RoadwayObserverSpec(id="lane1", lane_number=1, method="luminance", back_offset_m=40.0),
            RoadwayObserverSpec(id="lane2", lane_number=2, method="ti", back_offset_m=40.0),
        ],
    )
    grid = RoadwayGridSpec(id="rg", name="RG", lane_width=3.5, road_length=10.0, nx=2, ny=2, num_lanes=2)
    rows = resolve_observers(roadway, grid, origin=(0.0, 0.0, 0.0), lane_widths=[3.5, 3.5], settings={})
    assert len(rows) == 2
    assert rows[0]["observer_id"] == "lane1"
    assert rows[1]["observer_id"] == "lane2"
    assert rows[1]["method"] == "ti"


def test_roadway_results_json_is_deterministic(tmp_path: Path) -> None:
    project_a_root = tmp_path / "run_a"
    project_b_root = tmp_path / "run_b"
    project_a_root.mkdir(parents=True, exist_ok=True)
    project_b_root.mkdir(parents=True, exist_ok=True)

    pa = _seed_project(project_a_root)
    pb = _seed_project(project_b_root)

    ra = run_job_in_memory(pa, "j1")
    rb = run_job_in_memory(pb, "j1")

    results_a = json.loads((Path(ra.result_dir) / "results.json").read_text(encoding="utf-8"))
    results_b = json.loads((Path(rb.result_dir) / "results.json").read_text(encoding="utf-8"))

    assert results_a == results_b
    assert "lane_grids" in results_a
    assert "metadata" in results_a
    assert "observer_sets" in results_a
    assert results_a["observer_sets"]["ti_stub"]


def test_auto_observers_use_selected_observer_method() -> None:
    roadway = RoadwaySpec(
        id="rw",
        name="Road",
        start=(0.0, 0.0, 0.0),
        end=(10.0, 0.0, 0.0),
        num_lanes=2,
        lane_width=3.5,
    )
    grid = RoadwayGridSpec(
        id="rg",
        name="RG",
        lane_width=3.5,
        road_length=10.0,
        nx=2,
        ny=2,
        num_lanes=2,
        observer_method="en13201_m",
    )
    rows = resolve_observers(roadway, grid, origin=(0.0, 0.0, 0.0), lane_widths=[3.5, 3.5], settings={})
    assert len(rows) == 2
    assert all(str(r.get("method")) == "en13201_m" for r in rows)
