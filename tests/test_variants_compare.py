from __future__ import annotations

import json
from pathlib import Path

from luxera.project.io import save_project_schema
from luxera.project.schema import (
    CalcGrid,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    ProjectVariant,
    RotationSpec,
    TransformSpec,
)
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


def test_run_job_for_variants_writes_compare_artifacts(tmp_path: Path) -> None:
    ies = _ies_fixture(tmp_path / "variant.ies")
    project = Project(name="Variants", root_dir=str(tmp_path))
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Lum",
            photometry_asset_id="a1",
            transform=TransformSpec(
                position=(2.0, 2.0, 3.0),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0)),
            ),
            flux_multiplier=1.0,
        )
    )
    project.grids.append(CalcGrid(id="g1", name="G1", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3))
    project.jobs.append(JobSpec(id="j1", type="direct"))

    project.variants.append(ProjectVariant(id="base", name="Baseline"))
    project.variants.append(
        ProjectVariant(
            id="dim",
            name="Dimmed",
            diff_ops=[
                {
                    "op": "update",
                    "kind": "luminaire",
                    "id": "l1",
                    "payload": {"flux_multiplier": 0.5},
                }
            ],
        )
    )

    ppath = tmp_path / "p.json"
    save_project_schema(project, ppath)

    out = run_job_for_variants(ppath, "j1", ["base", "dim"])

    assert Path(out.compare_json).exists()
    assert Path(out.compare_csv).exists()
    payload = json.loads(Path(out.compare_json).read_text(encoding="utf-8"))
    assert payload["job_id"] == "j1"
    assert len(payload["rows"]) == 2
    assert payload["baseline_variant_id"] == "base"

    rows = {row["variant_id"]: row for row in payload["rows"]}
    assert rows["dim"]["mean_lux"] < rows["base"]["mean_lux"]
    assert rows["base"]["delta_mean_lux"] == 0.0
    assert rows["dim"]["delta_mean_lux"] < 0.0
