from __future__ import annotations

import json
import shutil
from pathlib import Path

from luxera.cli import main
from luxera.export.report_model import build_report_model
from luxera.project.io import load_project_schema
from luxera.project.schema import (
    CalcGrid,
    EmergencyModeSpec,
    EmergencySpec,
    EscapeRouteSpec,
    JobResultRef,
    JobSpec,
    OpeningSpec,
    Project,
)


def test_indoor_report_contract(tmp_path: Path) -> None:
    src = Path("examples/indoor_office").resolve()
    dst = tmp_path / "indoor_office"
    shutil.copytree(src, dst)
    project_path = dst / "office.luxera.json"

    assert main(["run-all", str(project_path), "--job", "office_direct", "--report", "--bundle"]) == 0

    project = load_project_schema(project_path)
    ref = next((r for r in project.results if r.job_id == "office_direct"), None)
    assert ref is not None
    result_dir = Path(ref.result_dir)

    manifest_path = result_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    meta = manifest.get("metadata", {})
    assert "job_hash" in meta
    assert "seed" in meta
    assert "solver_version" in meta
    assert "photometry_hashes" in meta
    assert "settings" in meta
    assert "coordinate_convention" in meta

    assert (result_dir / "grid.csv").exists()
    assert (result_dir / "summary.json").exists()
    assert (result_dir / "heatmap.png").exists()
    assert (result_dir / "report.pdf").exists()
    assert (result_dir / "audit_bundle.zip").exists()
    assert (result_dir / "report.pdf").stat().st_size > 1024

    pdf_text = (result_dir / "report.pdf").read_bytes().decode("latin-1", errors="ignore")
    assert "Indoor Office Hero" in pdf_text
    assert "Project Revision" in pdf_text
    assert "Job Hash" in pdf_text
    assert "Photometry Hashes" in pdf_text
    assert "Assumptions" in pdf_text
    assert "Luminaire Schedule" in pdf_text
    assert "Per-Grid Statistics" in pdf_text
    assert "Inputs" in pdf_text

    result_meta = json.loads((result_dir / "result.json").read_text(encoding="utf-8"))
    assumptions = result_meta.get("assumptions", [])
    assert any("occlusion" in str(a).lower() for a in assumptions)
    assert any("tilt" in str(a).lower() or "photometric" in str(a).lower() for a in assumptions)
    assert any("coordinate convention" in str(a).lower() for a in assumptions)

    report = build_report_model(project, "office_direct", ref)
    assert report.get("luminaire_schedule")
    tables = report.get("tables", {})
    assert isinstance(tables, dict)
    assert "calc_tables" in report
    assert "grids" in tables
    assert "vertical_planes" in tables
    assert "point_sets" in tables
    assert report.get("worst_case_summary")
    assumptions_report = report.get("audit", {}).get("assumptions", [])
    assert any("tilt" in str(a).lower() for a in assumptions_report)
    assert any("units" in str(a).lower() for a in assumptions_report)
    assert any("occlusion" in str(a).lower() for a in assumptions_report)

    calc_objects = result_meta.get("summary", {}).get("calc_objects", [])
    expected_rows = len(calc_objects) if isinstance(calc_objects, list) else 0
    actual_rows = (
        len(tables.get("grids", []))
        + len(tables.get("vertical_planes", []))
        + len(tables.get("point_sets", []))
    )
    assert actual_rows == expected_rows


def test_daylight_report_section_exists_for_daylight_job(tmp_path: Path) -> None:
    result_dir = tmp_path / "res_daylight"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "summary": {
                    "mode": "annual",
                    "sky": "CIE_overcast",
                    "calc_objects": [{"type": "grid", "id": "g1", "summary": {"mean_df_percent": 2.0}}],
                },
                "assets": {},
                "solver": {},
                "job": {},
            }
        ),
        encoding="utf-8",
    )
    p = Project(name="Daylight")
    p.geometry.openings.append(OpeningSpec(id="o1", name="w", opening_type="window", kind="window", is_daylight_aperture=True))
    p.grids.append(CalcGrid(id="g1", name="g", origin=(0, 0, 0), width=1, height=1, elevation=0.8, nx=2, ny=2))
    p.jobs.append(JobSpec(id="j1", type="daylight", backend="df"))
    ref = JobResultRef(job_id="j1", job_hash="h", result_dir=str(result_dir), summary={"mode": "annual"})
    report = build_report_model(p, "j1", ref)
    assert isinstance(report.get("daylight"), dict)
    assert report["daylight"].get("targets") is not None


def test_emergency_report_section_exists_for_emergency_job(tmp_path: Path) -> None:
    result_dir = tmp_path / "res_emergency"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "summary": {
                    "mode": "emergency_v1",
                    "route_results": [{"route_id": "r1", "min_lux": 0.8, "u0": 0.08}],
                    "open_area_results": [{"grid_id": "g1", "min_lux": 0.4, "u0": 0.09}],
                    "compliance": {"status": "FAIL", "thresholds": {"route_min_lux": 1.0}},
                    "emergency_factor": 0.5,
                    "luminaire_count": 1,
                },
                "assets": {},
                "solver": {},
                "job": {},
            }
        ),
        encoding="utf-8",
    )
    p = Project(name="Emergency")
    p.grids.append(CalcGrid(id="g1", name="g", origin=(0, 0, 0), width=1, height=1, elevation=0.0, nx=2, ny=2))
    p.escape_routes.append(EscapeRouteSpec(id="r1", polyline=[(0, 0, 0), (1, 0, 0)]))
    p.jobs.append(JobSpec(id="j1", type="emergency", emergency=EmergencySpec(standard="EN1838"), mode=EmergencyModeSpec(emergency_factor=0.5)))
    ref = JobResultRef(job_id="j1", job_hash="h", result_dir=str(result_dir), summary={"mode": "emergency_v1"})
    report = build_report_model(p, "j1", ref)
    assert isinstance(report.get("emergency"), dict)
    assert report["emergency"].get("route_table") is not None
