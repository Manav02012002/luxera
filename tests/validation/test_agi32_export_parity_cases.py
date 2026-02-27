from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from luxera.project.runner import run_job_in_memory
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def _case_files() -> list[Path]:
    root = Path(__file__).resolve().parent / "agi32_export_cases"
    return sorted(root.glob("case_*.json"))


def _load_case(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_project(case: dict, case_dir: Path, tmp_path: Path) -> Project:
    room = case["room"]
    grid = case["grid"]
    project = Project(name=str(case.get("id", "agi32_case")), root_dir=str(tmp_path / str(case.get("id", "agi32_case"))))
    project.geometry.rooms.append(
        RoomSpec(
            id="r1",
            name="Room",
            width=float(room["width"]),
            length=float(room["length"]),
            height=float(room["height"]),
            origin=(0.0, 0.0, 0.0),
            wall_reflectance=float(room["wall_reflectance"]),
            floor_reflectance=float(room["floor_reflectance"]),
            ceiling_reflectance=float(room["ceiling_reflectance"]),
        )
    )
    for i, lum in enumerate(case["luminaires"]):
        asset_id = f"a{i+1}"
        project.photometry_assets.append(PhotometryAsset(id=asset_id, format="IES", path=str((case_dir / str(lum["ies_file"])).resolve())))
        yaw, pitch, roll = [float(v) for v in lum.get("rotation", [0.0, 0.0, 0.0])]
        project.luminaires.append(
            LuminaireInstance(
                id=f"l{i+1}",
                name=f"Lum {i+1}",
                photometry_asset_id=asset_id,
                transform=TransformSpec(
                    position=tuple(float(v) for v in lum["position"]),
                    rotation=RotationSpec(type="euler_zyx", euler_deg=(yaw, pitch, roll)),
                ),
            )
        )
    project.grids.append(
        CalcGrid(
            id="g1",
            name="Workplane",
            origin=tuple(float(v) for v in grid["origin"]),
            width=float(grid["width"]),
            height=float(grid["height"]),
            elevation=float(grid["elevation"]),
            nx=int(grid["nx"]),
            ny=int(grid["ny"]),
            room_id="r1",
        )
    )
    project.jobs.append(JobSpec(id="j_direct", type="direct", settings={}, targets=["g1"]))
    return project


def _assert_close(name: str, actual: float, expected: float, rel: float, abs_: float) -> None:
    if not math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_):
        raise AssertionError(
            f"{name} mismatch: actual={actual:.6f}, expected={expected:.6f}, "
            f"abs_err={abs(actual-expected):.6f}, rel_tol={rel}, abs_tol={abs_}"
        )


def _assert_provenance(case: dict, case_dir: Path) -> None:
    expected = case.get("expected", {})
    prov = expected.get("provenance", {})
    if str(prov.get("source", "")).strip().lower() != "agi32_export":
        raise AssertionError(f"{case.get('id', 'unknown')} provenance.source must be 'agi32_export'")
    required = (
        "tool",
        "tool_version",
        "export_date",
        "raw_summary_file",
        "raw_summary_sha256",
    )
    for key in required:
        if not str(prov.get(key, "")).strip():
            raise AssertionError(f"{case.get('id', 'unknown')} missing provenance.{key}")

    raw_summary = (case_dir / str(prov["raw_summary_file"])).resolve()
    if not raw_summary.exists():
        raise AssertionError(f"Raw AGI32 summary file not found: {raw_summary}")
    if _sha256(raw_summary) != str(prov["raw_summary_sha256"]).strip().lower():
        raise AssertionError(f"Raw AGI32 summary SHA256 mismatch for {case.get('id', 'unknown')}")

    raw_grid_file = str(prov.get("raw_grid_file", "")).strip()
    raw_grid_sha = str(prov.get("raw_grid_sha256", "")).strip().lower()
    if raw_grid_file or raw_grid_sha:
        if not raw_grid_file or not raw_grid_sha:
            raise AssertionError(f"{case.get('id', 'unknown')} must provide both raw_grid_file and raw_grid_sha256")
        raw_grid = (case_dir / raw_grid_file).resolve()
        if not raw_grid.exists():
            raise AssertionError(f"Raw AGI32 grid file not found: {raw_grid}")
        if _sha256(raw_grid) != raw_grid_sha:
            raise AssertionError(f"Raw AGI32 grid SHA256 mismatch for {case.get('id', 'unknown')}")


@pytest.mark.validation
def test_agi32_export_parity_cases(tmp_path: Path) -> None:
    files = _case_files()
    if not files:
        pytest.skip("No AGI32 export parity cases found under tests/validation/agi32_export_cases.")

    for case_file in files:
        case = _load_case(case_file)
        _assert_provenance(case, case_file.parent)
        project = _build_project(case, case_file.parent, tmp_path)
        result = run_job_in_memory(project, "j_direct")
        summary = result.summary
        actual = {
            "min_lux": float(summary.get("min_lux", 0.0)),
            "max_lux": float(summary.get("max_lux", 0.0)),
            "avg_lux": float(summary.get("mean_lux", 0.0)),
            "uniformity_u0": float(summary.get("uniformity_ratio", 0.0)),
        }
        exp = case["expected"]
        tol = exp.get("tolerances", {})
        _assert_close("min_lux", actual["min_lux"], float(exp["min_lux"]), rel=float(tol.get("min_lux_pct", 0.05)), abs_=1e-9)
        _assert_close("max_lux", actual["max_lux"], float(exp["max_lux"]), rel=float(tol.get("max_lux_pct", 0.05)), abs_=1e-9)
        _assert_close("avg_lux", actual["avg_lux"], float(exp["avg_lux"]), rel=float(tol.get("avg_lux_pct", 0.03)), abs_=1e-9)
        _assert_close(
            "uniformity_u0",
            actual["uniformity_u0"],
            float(exp["uniformity_u0"]),
            rel=0.0,
            abs_=float(tol.get("uniformity_u0_abs", 0.02)),
        )
