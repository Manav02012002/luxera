from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

from luxera.project.io import load_project_schema
from luxera.project.runner import run_job_in_memory


def _scene_dirs() -> list[Path]:
    root = Path(__file__).resolve().parent / "scenes"
    return sorted([p for p in root.iterdir() if p.is_dir() and (p / "project.json").exists()])


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _absolutize_assets(project, scene_dir: Path) -> None:
    for asset in project.photometry_assets:
        if asset.path and not Path(asset.path).is_absolute():
            asset.path = str((scene_dir / asset.path).resolve())


def _grid_values(result_dir: str, grid_id: str = "g1") -> np.ndarray:
    p = Path(result_dir) / f"grid_{grid_id}.csv"
    if not p.exists():
        p = Path(result_dir) / "grid.csv"
    return np.loadtxt(p, delimiter=",", skiprows=1)[:, 3].reshape(-1)


def _translate_project(project, dx: float, dy: float) -> None:
    for room in project.geometry.rooms:
        x, y, z = room.origin
        room.origin = (x + dx, y + dy, z)
    for lum in project.luminaires:
        x, y, z = lum.transform.position
        lum.transform.position = (x + dx, y + dy, z)
    for grid in project.grids:
        x, y, z = grid.origin
        grid.origin = (x + dx, y + dy, z)
    for surf in project.geometry.surfaces:
        surf.vertices = [(x + dx, y + dy, z) for (x, y, z) in surf.vertices]
    for opn in project.geometry.openings:
        opn.vertices = [(x + dx, y + dy, z) for (x, y, z) in opn.vertices]
    for obs in project.geometry.obstructions:
        obs.vertices = [(x + dx, y + dy, z) for (x, y, z) in obs.vertices]


def _rotate_project_180_z(project) -> None:
    for room in project.geometry.rooms:
        x, y, z = room.origin
        room.origin = (-x - room.width, -y - room.length, z)
    for lum in project.luminaires:
        x, y, z = lum.transform.position
        lum.transform.position = (-x, -y, z)
    for grid in project.grids:
        x, y, z = grid.origin
        grid.origin = (-x - grid.width, -y - grid.height, z)
    for surf in project.geometry.surfaces:
        surf.vertices = [(-x, -y, z) for (x, y, z) in surf.vertices]
    for opn in project.geometry.openings:
        opn.vertices = [(-x, -y, z) for (x, y, z) in opn.vertices]
    for obs in project.geometry.obstructions:
        obs.vertices = [(-x, -y, z) for (x, y, z) in obs.vertices]


def _scale_project_to_feet(project) -> None:
    scale = 1.0 / 0.3048
    project.geometry.length_unit = "ft"
    project.geometry.scale_to_meters = 0.3048

    for room in project.geometry.rooms:
        room.origin = tuple(float(v) * scale for v in room.origin)
        room.width *= scale
        room.length *= scale
        room.height *= scale
    for lum in project.luminaires:
        lum.transform.position = tuple(float(v) * scale for v in lum.transform.position)
    for grid in project.grids:
        grid.origin = tuple(float(v) * scale for v in grid.origin)
        grid.width *= scale
        grid.height *= scale
        grid.elevation *= scale
    for surf in project.geometry.surfaces:
        surf.vertices = [(x * scale, y * scale, z * scale) for (x, y, z) in surf.vertices]
    for opn in project.geometry.openings:
        opn.vertices = [(x * scale, y * scale, z * scale) for (x, y, z) in opn.vertices]
    for obs in project.geometry.obstructions:
        obs.vertices = [(x * scale, y * scale, z * scale) for (x, y, z) in obs.vertices]
        if obs.height is not None:
            obs.height *= scale


def test_validation_scene_invariances() -> None:
    for scene_dir in _scene_dirs():
        inv = _read_json(scene_dir / "expected_invariances.json")

        base = load_project_schema(scene_dir / "project.json")
        _absolutize_assets(base, scene_dir)
        base_ref = run_job_in_memory(base, "j_direct")
        base_vals = _grid_values(base_ref.result_dir)

        if bool(inv.get("translation_invariance", False)):
            p = copy.deepcopy(base)
            _translate_project(p, dx=7.25, dy=-4.5)
            vals = _grid_values(run_job_in_memory(p, "j_direct").result_dir)
            assert np.allclose(base_vals, vals, rtol=1e-5, atol=1e-5), f"translation invariance failed for {scene_dir.name}"

        if bool(inv.get("rotation_invariance_z", False)):
            p = copy.deepcopy(base)
            _rotate_project_180_z(p)
            vals = _grid_values(run_job_in_memory(p, "j_direct").result_dir)
            assert np.allclose(base_vals, vals, rtol=1e-5, atol=1e-5), f"rotation invariance failed for {scene_dir.name}"

        if bool(inv.get("scale_invariance_units", False)):
            p = copy.deepcopy(base)
            _scale_project_to_feet(p)
            vals = _grid_values(run_job_in_memory(p, "j_direct").result_dir)
            assert np.allclose(base_vals, vals, rtol=1e-5, atol=1e-5), f"scale invariance failed for {scene_dir.name}"

        tilt_cfg = inv.get("tilt_file_vs_none")
        if isinstance(tilt_cfg, dict):
            none_asset = str(tilt_cfg.get("none_asset", "")).strip()
            expect = str(tilt_cfg.get("expect", "lower")).strip().lower()
            min_relative_delta = float(tilt_cfg.get("min_relative_delta", 0.0))
            assert none_asset, f"tilt_file_vs_none.none_asset missing for {scene_dir.name}"
            p = copy.deepcopy(base)
            assert p.photometry_assets, f"No photometry assets for {scene_dir.name}"
            p.photometry_assets[0].path = str((scene_dir / none_asset).resolve())
            none_vals = _grid_values(run_job_in_memory(p, "j_direct").result_dir)
            base_mean = float(np.mean(base_vals))
            none_mean = float(np.mean(none_vals))
            if expect == "lower":
                assert base_mean < none_mean, f"tilt expected lower than none for {scene_dir.name}"
            elif expect == "higher":
                assert base_mean > none_mean, f"tilt expected higher than none for {scene_dir.name}"
            rel_delta = abs(base_mean - none_mean) / max(abs(none_mean), 1e-9)
            assert rel_delta >= min_relative_delta, f"tilt relative delta below minimum for {scene_dir.name}"
