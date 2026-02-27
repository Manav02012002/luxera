from __future__ import annotations

import json
from pathlib import Path

from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec
from luxera.runner import run_job_in_memory as run_job


IES_TEXT = """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
"""


def _base_project(tmp_path: Path, lum_z: float) -> Project:
    ies_path = tmp_path / "fixture.ies"
    ies_path.write_text(IES_TEXT, encoding="utf-8")

    p = Project(name="NearField", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(0.0, 0.0, lum_z), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="grid", origin=(-0.5, -0.5, 0.0), width=1.0, height=1.0, elevation=0.9, nx=3, ny=3))
    p.jobs.append(JobSpec(id="j1", type="direct", seed=7))
    return p


def test_near_field_warning_triggers_for_close_distances(tmp_path: Path) -> None:
    project_path = tmp_path / "proj.json"
    save_project_schema(_base_project(tmp_path, lum_z=1.0), project_path)
    p = load_project_schema(project_path)
    ref = run_job(p, "j1")

    payload = json.loads((Path(ref.result_dir) / "result.json").read_text(encoding="utf-8"))
    warnings = payload.get("near_field_warnings", [])
    assert isinstance(warnings, list) and warnings
    w = warnings[0]
    assert w.get("code") == "near_field_photometry_risk"
    assert w.get("luminaire_id") == "l1"
    assert w.get("affected_grids") == ["g1"]
    assert "near-field" in str(w.get("message", "")).lower()
    assert "increase mounting height" in str(w.get("mitigation", "")).lower()


def test_near_field_warning_not_emitted_for_far_field(tmp_path: Path) -> None:
    project_path = tmp_path / "proj.json"
    save_project_schema(_base_project(tmp_path, lum_z=10.0), project_path)
    p = load_project_schema(project_path)
    ref = run_job(p, "j1")

    payload = json.loads((Path(ref.result_dir) / "result.json").read_text(encoding="utf-8"))
    warnings = payload.get("near_field_warnings", [])
    assert warnings == []
