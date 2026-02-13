from __future__ import annotations

import json
from pathlib import Path

from luxera.project.io import save_project_schema
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, ProjectVariant, RotationSpec, TransformSpec
from luxera.project.variants import run_job_for_variants


def _ies_fixture(path: Path) -> Path:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1000 700 300
""",
        encoding="utf-8",
    )
    return path


def test_variants_compare_artifacts_exist_and_match(tmp_path: Path) -> None:
    ies = _ies_fixture(tmp_path / "v.ies")
    p = Project(name="Variants", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 2.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="G", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3))
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu"))
    p.variants.append(ProjectVariant(id="base", name="Base", diff_ops=[]))
    p.variants.append(ProjectVariant(id="alt", name="Alt", diff_ops=[]))
    project_path = tmp_path / "project.json"
    save_project_schema(p, project_path)

    res = run_job_for_variants(project_path, "j1", ["base", "alt"], baseline_variant_id="base")
    assert Path(res.compare_csv).exists()
    assert Path(res.compare_json).exists()
    payload = json.loads(Path(res.compare_json).read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    assert len(rows) == len(res.rows)
