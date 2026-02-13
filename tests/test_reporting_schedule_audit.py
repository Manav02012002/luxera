from __future__ import annotations

import json
from pathlib import Path

from luxera.project.schema import JobResultRef, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec
from luxera.reporting.audit import load_audit_metadata
from luxera.reporting.schedules import build_luminaire_schedule


def test_reporting_schedule_groups_luminaires() -> None:
    p = Project(name="R")
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path="fixture.ies"))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(0.0, 0.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    p.luminaires.append(
        LuminaireInstance(
            id="l2",
            name="L2",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(1.0, 0.0, 2.8), rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))),
        )
    )
    rows = build_luminaire_schedule(p, {"a1": "hash123"})
    assert len(rows) == 1
    assert int(rows[0]["count"]) == 2


def test_reporting_audit_loader(tmp_path: Path) -> None:
    rdir = tmp_path / "r"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "result.json").write_text(
        json.dumps(
            {
                "job_id": "j1",
                "job_hash": "h1",
                "seed": 0,
                "solver": {"package_version": "x"},
                "backend": {"name": "cpu"},
                "units": {"length": "m", "illuminance": "lux"},
                "coordinate_convention": "local",
                "assumptions": ["a1"],
                "unsupported_features": ["u1"],
            }
        ),
        encoding="utf-8",
    )
    out = load_audit_metadata(rdir)
    assert out["job_id"] == "j1"
    assert out["backend"]["name"] == "cpu"

