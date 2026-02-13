from __future__ import annotations

import json
from pathlib import Path

from luxera.project.schema import (
    CalcGrid,
    EmergencyModeSpec,
    EmergencySpec,
    EscapeRouteSpec,
    JobSpec,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RotationSpec,
    TransformSpec,
)
from luxera.runner import run_job_in_memory as run_job


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


def test_emergency_job_contract_artifacts(tmp_path: Path) -> None:
    ies = _ies_fixture(tmp_path / "em_contract.ies")
    p = Project(name="EmergencyContract", root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(2.0, 1.0, 2.8), rotation=rot),
        )
    )
    p.grids.append(CalcGrid(id="g1", name="open_area", origin=(0.0, 0.0, 0.0), width=4.0, height=2.0, elevation=0.0, nx=5, ny=3))
    p.escape_routes.append(EscapeRouteSpec(id="r1", name="route", polyline=[(0.0, 1.0, 0.0), (4.0, 1.0, 0.0)], width_m=1.0, spacing_m=0.5))
    p.jobs.append(
        JobSpec(
            id="j1",
            type="emergency",
            emergency=EmergencySpec(standard="EN1838", route_min_lux=0.1, route_u0_min=0.01, open_area_min_lux=0.1, open_area_u0_min=0.01),
            mode=EmergencyModeSpec(emergency_factor=0.5),
            routes=["r1"],
            open_area_targets=["g1"],
        )
    )
    ref = run_job(p, "j1")
    out_dir = Path(ref.result_dir)
    assert (out_dir / "escape_route_r1.csv").exists()
    assert (out_dir / "open_area_g1.csv").exists()
    assert (out_dir / "emergency_summary.json").exists()
    summary = json.loads((out_dir / "emergency_summary.json").read_text(encoding="utf-8"))
    assert "route_results" in summary
    assert "open_area_results" in summary
    assert "compliance" in summary
