from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from luxera.project.runner import run_job_in_memory
from luxera.project.schema import (
    CalcGrid,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RoomSpec,
    RotationSpec,
    TransformSpec,
)


def _case_files() -> list[Path]:
    root = Path(__file__).resolve().parent / "manual_direct_reference_cases"
    return sorted(root.glob("manual_direct_case_*.json"))


def _load_case(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _grid_points(grid: dict) -> list[tuple[float, float, float]]:
    nx = int(grid["nx"])
    ny = int(grid["ny"])
    dx = float(grid["width"]) / max(nx - 1, 1)
    dy = float(grid["height"]) / max(ny - 1, 1)
    ox, oy, _ = [float(v) for v in grid["origin"]]
    z = float(grid["elevation"])
    out: list[tuple[float, float, float]] = []
    for j in range(ny):
        for i in range(nx):
            out.append((ox + i * dx, oy + j * dy, z))
    return out


def _direct_lux(point: tuple[float, float, float], luminaire: dict) -> float:
    x, y, z = point
    lx, ly, lz = [float(v) for v in luminaire["position"]]
    intensity_cd = float(luminaire["intensity_cd"])
    dx = lx - x
    dy = ly - y
    dz = lz - z
    d2 = dx * dx + dy * dy + dz * dz
    if d2 <= 1e-12:
        return 0.0
    d = math.sqrt(d2)
    cos_incidence = max(dz / d, 0.0)
    return intensity_cd * cos_incidence / d2


def _manual_metrics(case: dict) -> dict[str, float]:
    values: list[float] = []
    points = _grid_points(case["grid"])
    for point in points:
        lux = 0.0
        for lum in case["luminaires"]:
            lux += _direct_lux(point, lum)
        values.append(lux)
    min_lux = float(min(values))
    max_lux = float(max(values))
    avg_lux = float(sum(values) / len(values))
    uniformity = float(min_lux / avg_lux) if avg_lux > 1e-12 else 0.0
    return {
        "min_lux": min_lux,
        "max_lux": max_lux,
        "avg_lux": avg_lux,
        "uniformity_u0": uniformity,
    }


def _build_project(case: dict, case_path: Path, tmp_path: Path) -> Project:
    room = case["room"]
    grid = case["grid"]
    project = Project(name=str(case["id"]), root_dir=str(tmp_path / str(case["id"])))
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
        project.photometry_assets.append(
            PhotometryAsset(
                id=asset_id,
                format="IES",
                path=str((case_path.parent / str(lum["ies_file"])).resolve()),
            )
        )
        yaw, pitch, roll = [float(v) for v in lum.get("rotation", [0.0, 0.0, 0.0])]
        project.luminaires.append(
            LuminaireInstance(
                id=f"l{i+1}",
                name=f"Luminaire {i+1}",
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


def _assert_with_tolerance(metric: str, actual: float, expected: float, rel_tol: float, abs_tol: float) -> None:
    delta = abs(actual - expected)
    if not math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol):
        raise AssertionError(
            f"{metric} mismatch: actual={actual:.8f}, expected={expected:.8f}, "
            f"abs_err={delta:.8f}, rel_tol={rel_tol}, abs_tol={abs_tol}"
        )


@pytest.mark.validation
def test_manual_direct_reference_cases(tmp_path: Path) -> None:
    files = _case_files()
    assert len(files) == 10, "Expected exactly 10 manual direct reference cases"

    for case_file in files:
        case = _load_case(case_file)
        expected = case["expected"]
        if "provenance" not in expected or "source" not in expected["provenance"]:
            raise AssertionError(f"{case['id']} missing expected.provenance.source")

        manual = _manual_metrics(case)
        _assert_with_tolerance("manual_min_lux", manual["min_lux"], float(expected["min_lux"]), rel_tol=1e-9, abs_tol=1e-9)
        _assert_with_tolerance("manual_max_lux", manual["max_lux"], float(expected["max_lux"]), rel_tol=1e-9, abs_tol=1e-9)
        _assert_with_tolerance("manual_avg_lux", manual["avg_lux"], float(expected["avg_lux"]), rel_tol=1e-9, abs_tol=1e-9)
        _assert_with_tolerance(
            "manual_uniformity_u0",
            manual["uniformity_u0"],
            float(expected["uniformity_u0"]),
            rel_tol=1e-9,
            abs_tol=1e-9,
        )

        project = _build_project(case, case_file, tmp_path)
        result = run_job_in_memory(project, "j_direct")
        summary = result.summary
        actual = {
            "min_lux": float(summary.get("min_lux", 0.0)),
            "max_lux": float(summary.get("max_lux", 0.0)),
            "avg_lux": float(summary.get("mean_lux", 0.0)),
            "uniformity_u0": float(summary.get("uniformity_ratio", 0.0)),
        }
        tol = expected["tolerances"]
        _assert_with_tolerance(
            "engine_min_lux",
            actual["min_lux"],
            float(expected["min_lux"]),
            rel_tol=float(tol["min_lux_pct"]),
            abs_tol=1e-9,
        )
        _assert_with_tolerance(
            "engine_max_lux",
            actual["max_lux"],
            float(expected["max_lux"]),
            rel_tol=float(tol["max_lux_pct"]),
            abs_tol=1e-9,
        )
        _assert_with_tolerance(
            "engine_avg_lux",
            actual["avg_lux"],
            float(expected["avg_lux"]),
            rel_tol=float(tol["avg_lux_pct"]),
            abs_tol=1e-9,
        )
        _assert_with_tolerance(
            "engine_uniformity_u0",
            actual["uniformity_u0"],
            float(expected["uniformity_u0"]),
            rel_tol=0.0,
            abs_tol=float(tol["uniformity_u0_abs"]),
        )
