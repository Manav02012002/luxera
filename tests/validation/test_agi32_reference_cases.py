from __future__ import annotations

import json
from pathlib import Path

import pytest

from luxera.project.runner import run_job_in_memory
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RoomSpec, RotationSpec, TransformSpec


def _reference_case_files() -> list[Path]:
    root = Path(__file__).resolve().parent / "reference_cases"
    return sorted(p for p in root.glob("case_*.json") if p.is_file())


def _load_case(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_project(case: dict, case_dir: Path, tmp_path: Path) -> Project:
    room = case["room"]
    grid = case["grid"]

    project = Project(name=str(case.get("id", path_safe(case_dir.name))), root_dir=str(tmp_path / case.get("id", "ref_case")))
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
        ies_path = (case_dir / str(lum["ies_file"])).resolve()
        project.photometry_assets.append(
            PhotometryAsset(id=asset_id, format="IES", path=str(ies_path))
        )
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

    project.jobs.append(JobSpec(id="j_direct", type="direct", settings={}))
    return project


def _assert_reference(case_id: str, actual: dict[str, float], expected: dict) -> None:
    tol = expected.get("tolerances", {})

    checks = [
        ("min_lux", float(expected["min_lux"]), float(actual["min_lux"]), float(tol.get("min_lux_pct", 0.15)), "pct"),
        ("max_lux", float(expected["max_lux"]), float(actual["max_lux"]), float(tol.get("max_lux_pct", 0.15)), "pct"),
        ("avg_lux", float(expected["avg_lux"]), float(actual["avg_lux"]), float(tol.get("avg_lux_pct", 0.10)), "pct"),
        (
            "uniformity_u0",
            float(expected["uniformity_u0"]),
            float(actual["uniformity_u0"]),
            float(tol.get("uniformity_u0_abs", 0.05)),
            "abs",
        ),
    ]

    failures: list[str] = []
    rows = ["metric          expected    actual      delta       tolerance", "---------------------------------------------------------------"]
    for metric, exp, act, tval, mode in checks:
        delta = act - exp
        if mode == "pct":
            rel = abs(delta) / max(abs(exp), 1e-9)
            ok = rel <= tval
            tol_text = f"±{100.0*tval:.1f}%"
            delta_text = f"{100.0*rel:.2f}%"
        else:
            ok = abs(delta) <= tval
            tol_text = f"±{tval:.3f}"
            delta_text = f"{delta:+.3f}"
        rows.append(f"{metric:<15} {exp:>9.3f} {act:>9.3f} {delta_text:>10} {tol_text:>12}")
        if not ok:
            failures.append(metric)

    if failures:
        table = "\n".join(rows)
        raise AssertionError(f"Reference mismatch for {case_id}: {', '.join(failures)}\n{table}")


def _assert_case1_lumen_method_sanity(case: dict, actual_avg_lux: float) -> None:
    """
    Independent ballpark check for case 1 using lumen method.

    E_avg ~= (Phi * UF * MF) / A
    For a small enclosed room with one broad downlight, UF in [0.45, 0.60]
    and MF ~= 1.0 is a practical sanity range.
    """
    if str(case.get("id", "")) != "case_01_single_downlight_4x4":
        return
    room = case["room"]
    area = float(room["width"]) * float(room["length"])
    phi = 10000.0
    e_low = (phi * 0.45 * 1.0) / max(area, 1e-9)
    e_high = (phi * 0.60 * 1.0) / max(area, 1e-9)
    assert e_low <= actual_avg_lux <= e_high, (
        f"Case 1 lumen-method sanity failed: avg_lux={actual_avg_lux:.2f}, "
        f"expected range=[{e_low:.2f}, {e_high:.2f}]"
    )


@pytest.mark.validation
def test_synthetic_reference_cases(tmp_path: Path) -> None:
    case_files = _reference_case_files()
    assert case_files, "No synthetic reference case files found"

    for case_file in case_files:
        case = _load_case(case_file)
        project = _build_project(case, case_file.parent, tmp_path)
        ref = run_job_in_memory(project, "j_direct")

        summary = ref.summary
        actual = {
            "min_lux": float(summary.get("min_lux", 0.0)),
            "max_lux": float(summary.get("max_lux", 0.0)),
            "avg_lux": float(summary.get("mean_lux", 0.0)),
            "uniformity_u0": float(summary.get("uniformity_ratio", 0.0)),
        }
        prov = case.get("expected", {}).get("provenance", {})
        if not isinstance(prov, dict) or "source" not in prov:
            raise AssertionError(
                f"Reference case {case.get('id', case_file.stem)} missing provenance metadata. "
                "Expected expected.provenance.source."
            )
        if str(prov.get("source", "")).strip().lower() != "synthetic_regression_baseline":
            raise AssertionError(
                f"Case {case.get('id', case_file.stem)} is not a synthetic regression case. "
                "Use tests/validation/test_agi32_export_parity_cases.py for AGI32 export parity."
            )
        _assert_reference(str(case.get("id", case_file.stem)), actual, case["expected"])
        _assert_case1_lumen_method_sanity(case, actual["avg_lux"])


def path_safe(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in s)
