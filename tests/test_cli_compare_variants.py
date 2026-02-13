from __future__ import annotations

import json
from pathlib import Path

from luxera.cli import main
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


def test_cli_compare_variants(tmp_path: Path) -> None:
    ies = _ies_fixture(tmp_path / "variant.ies")
    p = Project(name="VarCLI", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    p.luminaires.append(
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
    p.grids.append(CalcGrid(id="g1", name="G1", origin=(0.0, 0.0, 0.0), width=4.0, height=4.0, elevation=0.8, nx=3, ny=3))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    p.variants.append(ProjectVariant(id="base", name="Baseline"))
    p.variants.append(
        ProjectVariant(
            id="dim",
            name="Dimmed",
            diff_ops=[{"op": "update", "kind": "luminaire", "id": "l1", "payload": {"flux_multiplier": 0.5}}],
        )
    )

    proj = tmp_path / "project.json"
    save_project_schema(p, proj)

    rc = main(["compare-variants", str(proj), "j1", "--variants", "base,dim", "--baseline", "base"])
    assert rc == 0

    compare_dirs = sorted((tmp_path / ".luxera" / "results").glob("variants_*"))
    assert compare_dirs
    payload = json.loads((compare_dirs[-1] / "variants_compare.json").read_text(encoding="utf-8"))
    assert payload["baseline_variant_id"] == "base"
    rows = {row["variant_id"]: row for row in payload["rows"]}
    assert rows["dim"]["mean_lux"] < rows["base"]["mean_lux"]
    assert rows["dim"]["delta_mean_lux"] < 0.0
