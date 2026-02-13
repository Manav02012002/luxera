from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from luxera.project.runner import run_job_in_memory
from luxera.project.schema import (
    CalcGrid,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RotationSpec,
    TransformSpec,
)


def _ies_fixture(path: Path) -> Path:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 1000 1000
""",
        encoding="utf-8",
    )
    return path


def _build_project(tmp_path: Path, *, unit: str, scale_to_m: float) -> Project:
    p = Project(name=f"Units-{unit}", root_dir=str(tmp_path))
    p.geometry.length_unit = unit  # type: ignore[assignment]
    p.geometry.scale_to_meters = scale_to_m

    d = 1.0 / scale_to_m
    ies = _ies_fixture(tmp_path / "fixture.ies")
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0 * d, 2.0 * d, 3.0 * d), rotation=rot),
        )
    )
    p.grids.append(
        CalcGrid(
            id="g1",
            name="G1",
            origin=(1.0 * d, 1.0 * d, 0.0),
            width=2.0 * d,
            height=2.0 * d,
            elevation=0.8 * d,
            nx=3,
            ny=3,
        )
    )
    p.jobs.append(JobSpec(id="j1", type="direct", settings={"use_occlusion": False}))
    return p


def _grid_values(ref_dir: str) -> np.ndarray:
    grid = np.loadtxt(Path(ref_dir) / "grid.csv", delimiter=",", skiprows=1)
    return np.asarray(grid[:, 3], dtype=float)


def test_direct_units_scale_invariance_m_vs_ft(tmp_path: Path) -> None:
    p_m = _build_project(tmp_path, unit="m", scale_to_m=1.0)
    ref_m = run_job_in_memory(p_m, "j1")
    vals_m = _grid_values(ref_m.result_dir)

    p_ft = _build_project(tmp_path, unit="ft", scale_to_m=0.3048)
    ref_ft = run_job_in_memory(p_ft, "j1")
    vals_ft = _grid_values(ref_ft.result_dir)

    assert vals_m.shape == vals_ft.shape
    assert np.allclose(vals_m, vals_ft, rtol=1e-6, atol=1e-8)

    s_m = json.loads((Path(ref_m.result_dir) / "summary.json").read_text(encoding="utf-8"))
    s_ft = json.loads((Path(ref_ft.result_dir) / "summary.json").read_text(encoding="utf-8"))
    assert abs(float(s_m["mean_lux"]) - float(s_ft["mean_lux"])) <= 1e-6


def test_direct_units_scale_invariance_m_vs_cm(tmp_path: Path) -> None:
    p_m = _build_project(tmp_path, unit="m", scale_to_m=1.0)
    ref_m = run_job_in_memory(p_m, "j1")
    vals_m = _grid_values(ref_m.result_dir)

    p_cm = _build_project(tmp_path, unit="cm", scale_to_m=0.01)
    ref_cm = run_job_in_memory(p_cm, "j1")
    vals_cm = _grid_values(ref_cm.result_dir)

    assert vals_m.shape == vals_cm.shape
    assert np.allclose(vals_m, vals_cm, rtol=1e-6, atol=1e-8)
