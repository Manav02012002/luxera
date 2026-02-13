from __future__ import annotations

import csv
from pathlib import Path

import pytest

from luxera.geometry.core import Transform, Vector3
from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec
from luxera.runner import run_job


_AZI_IES = """IESNA:LM-63-2019
TILT=NONE
1 1000 4 3 1 1 2 0.5 0.5 0.2
0 90 180 270
0 45 90
900 900 900
100 100 100
10 10 10
100 100 100
"""


def _write_project(tmp_path: Path, *, yaw_deg: float, name: str) -> Path:
    ies = tmp_path / "azi.ies"
    ies.write_text(_AZI_IES, encoding="utf-8")
    p = Project(name=name, root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(
                position=(0.0, 0.0, 2.0),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(yaw_deg, 0.0, 0.0)),
            ),
        )
    )
    p.grids.append(
        CalcGrid(
            id="g1",
            name="G1",
            origin=(-1.0, -1.0, 0.0),
            width=2.0,
            height=2.0,
            elevation=0.0,
            nx=7,
            ny=7,
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", seed=7))
    project_path = tmp_path / f"{name}.json"
    save_project_schema(p, project_path)
    return project_path


def _load_grid_map(grid_csv: Path) -> dict[tuple[float, float], float]:
    out: dict[tuple[float, float], float] = {}
    with grid_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            x = round(float(row["x"]), 6)
            y = round(float(row["y"]), 6)
            out[(x, y)] = float(row["illuminance"])
    return out


def test_yaw_axis_sanity() -> None:
    t = Transform.from_euler_zyx(Vector3(0.0, 0.0, 0.0), yaw_deg=90.0, pitch_deg=0.0, roll_deg=0.0)
    w = t.transform_direction(Vector3(1.0, 0.0, 0.0))
    assert w.x == pytest.approx(0.0, abs=1e-9)
    assert w.y == pytest.approx(1.0, abs=1e-9)
    assert w.z == pytest.approx(0.0, abs=1e-9)


def test_pitch_axis_sanity() -> None:
    t = Transform.from_euler_zyx(Vector3(0.0, 0.0, 0.0), yaw_deg=0.0, pitch_deg=90.0, roll_deg=0.0)
    w = t.transform_direction(Vector3(0.0, 0.0, 1.0))
    assert w.x == pytest.approx(1.0, abs=1e-9)
    assert w.y == pytest.approx(0.0, abs=1e-9)
    assert w.z == pytest.approx(0.0, abs=1e-9)


def test_luminaire_rotation_rotates_field_via_runner(tmp_path: Path) -> None:
    p0 = _write_project(tmp_path, yaw_deg=0.0, name="proj_y0")
    p1 = _write_project(tmp_path, yaw_deg=90.0, name="proj_y90")

    r0 = run_job(p0, "j1")
    r1 = run_job(p1, "j1")
    m0 = _load_grid_map(Path(r0.result_dir) / "grid.csv")
    m1 = _load_grid_map(Path(r1.result_dir) / "grid.csv")

    # 90 deg yaw around +Z should rotate field: E1(x,y) ~= E0(-y, x)
    for (x, y), e1 in m1.items():
        key0 = (round(-y, 6), round(x, 6))
        assert key0 in m0
        assert e1 == pytest.approx(m0[key0], rel=1e-4, abs=1e-8)
