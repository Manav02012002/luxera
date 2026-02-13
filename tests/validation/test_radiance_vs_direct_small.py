from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from luxera.backends import radiance as rad
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
    p = Project(name="rad-vs-cpu", root_dir=str(tmp_path))
    ies = _ies_fixture(tmp_path / "fixture.ies")
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 3.0), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="g", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3))
    return p


def test_radiance_validation_small_scene(monkeypatch, tmp_path: Path) -> None:
    project = _seed_project(tmp_path)
    project.jobs.append(JobSpec(id="cpu", type="direct", backend="cpu"))
    cpu_ref = run_job_in_memory(project, "cpu")
    cpu_vals = np.loadtxt(Path(cpu_ref.result_dir) / "grid.csv", delimiter=",", skiprows=1)[:, 3]
    cpu_summary = json.loads((Path(cpu_ref.result_dir) / "summary.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(rad.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    def fake_check_call(cmd, stdout=None, stderr=None):  # noqa: ARG001
        if stdout is not None:
            stdout.write(b"OCT")
        return 0

    def fake_check_output(cmd, stderr=None, text=False, input=None):  # noqa: ARG001
        if "-version" in cmd:
            return "rtrace 5.4a"
        # Produce RGB rows that map back close to CPU lux via Lux = 120*G
        g = cpu_vals / 120.0
        payload = "\n".join(f"0 {x:.9f} 0" for x in g).encode("utf-8")
        return payload.decode("utf-8") if text else payload

    monkeypatch.setattr(rad.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(rad.subprocess, "check_output", fake_check_output)

    out_dir = tmp_path / "rad"
    out_dir.mkdir()
    rr = rad.run_radiance_direct(project, JobSpec(id="rad", type="direct", backend="radiance"), out_dir)
    rad_vals = np.asarray(rr.result_data["grid_values"], dtype=float).reshape(-1)

    mean_abs = float(np.mean(np.abs(cpu_vals - rad_vals)))
    mean_rel = float(mean_abs / max(float(np.mean(cpu_vals)), 1e-9))
    assert mean_rel <= 0.05
    assert abs(float(cpu_summary["mean_lux"]) - float(np.mean(rad_vals))) / max(float(cpu_summary["mean_lux"]), 1e-9) <= 0.05
