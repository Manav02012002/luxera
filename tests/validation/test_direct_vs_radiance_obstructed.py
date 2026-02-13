from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from luxera.backends import radiance as rad
from luxera.project.io import load_project_schema
from luxera.project.runner import run_job_in_memory
from luxera.project.schema import JobSpec

pytestmark = pytest.mark.radiance


def _scene_dir() -> Path:
    return Path(__file__).resolve().parent / "scenes" / "obstructed"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _grid_values(result_dir: str) -> np.ndarray:
    return np.loadtxt(Path(result_dir) / "grid.csv", delimiter=",", skiprows=1)[:, 3].reshape(-1)


def _absolutize_asset_paths(project, scene_dir: Path) -> None:
    for asset in project.photometry_assets:
        if asset.path and not Path(asset.path).is_absolute():
            asset.path = str((scene_dir / asset.path).resolve())


def _mock_radiance(monkeypatch: pytest.MonkeyPatch, cpu_vals: np.ndarray, scale: float = 1.0) -> None:
    monkeypatch.setattr(rad.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    def fake_check_call(cmd, stdout=None, stderr=None):  # noqa: ARG001
        if stdout is not None:
            stdout.write(b"OCT")
        return 0

    def fake_check_output(cmd, stderr=None, text=False, input=None):  # noqa: ARG001
        if "-version" in cmd:
            return "rtrace 5.4a"
        g = (cpu_vals * scale) / 120.0
        payload = "\n".join(f"0 {x:.9f} 0" for x in g).encode("utf-8")
        return payload.decode("utf-8") if text else payload

    monkeypatch.setattr(rad.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(rad.subprocess, "check_output", fake_check_output)


def _assert_translation_invariance(scene_project_path: Path) -> None:
    scene_dir = scene_project_path.parent
    p0 = load_project_schema(scene_project_path)
    _absolutize_asset_paths(p0, scene_dir)
    v0 = _grid_values(run_job_in_memory(p0, "j_direct").result_dir)

    p1 = copy.deepcopy(p0)
    dx, dy = 6.0, 3.5
    for room in p1.geometry.rooms:
        ox, oy, oz = room.origin
        room.origin = (ox + dx, oy + dy, oz)
    for lum in p1.luminaires:
        x, y, z = lum.transform.position
        lum.transform.position = (x + dx, y + dy, z)
    for grid in p1.grids:
        x, y, z = grid.origin
        grid.origin = (x + dx, y + dy, z)
    for obs in p1.geometry.obstructions:
        obs.vertices = [(x + dx, y + dy, z) for (x, y, z) in obs.vertices]
    v1 = _grid_values(run_job_in_memory(p1, "j_direct").result_dir)
    assert np.allclose(v0, v1, rtol=1e-5, atol=1e-5)


def test_direct_vs_radiance_obstructed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    scene = _scene_dir()
    tol = _read_json(scene / "tolerance_band.json")
    inv = _read_json(scene / "expected_invariances.json")
    project = load_project_schema(scene / "project.json")
    _absolutize_asset_paths(project, scene)

    cpu_vals = _grid_values(run_job_in_memory(project, "j_direct").result_dir)

    _mock_radiance(monkeypatch, cpu_vals, scale=1.0)
    out_dir = tmp_path / "obstructed_rad"
    out_dir.mkdir()
    rad_result = rad.run_radiance_direct(project, JobSpec(id="j_rad", type="direct", backend="radiance"), out_dir)
    rad_vals = np.asarray(rad_result.result_data["grid_values"], dtype=float).reshape(-1)

    mean_abs = float(np.mean(np.abs(cpu_vals - rad_vals)))
    mean_rel = float(mean_abs / max(float(np.mean(cpu_vals)), 1e-9))
    assert mean_abs <= float(tol["mean_abs_error_max_lux"])
    assert mean_rel <= float(tol["mean_rel_error_max"])

    if bool(inv.get("translation_invariance", False)):
        _assert_translation_invariance(scene / "project.json")
