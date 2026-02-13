from __future__ import annotations

import json
from pathlib import Path

from luxera.project.schema import CalcGrid, DaylightSpec, JobSpec, OpeningSpec, Project
from luxera.runner import run_job_in_memory as run_job


def test_daylight_df_contract_artifacts(tmp_path: Path) -> None:
    p = Project(name="DaylightDF", root_dir=str(tmp_path))
    p.geometry.openings.append(
        OpeningSpec(
            id="op1",
            name="Window",
            kind="window",
            vertices=[(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 0.0, 2.5), (0.0, 0.0, 2.5)],
            is_daylight_aperture=True,
            visible_transmittance=0.65,
        )
    )
    p.grids.append(
        CalcGrid(
            id="g1",
            name="Grid",
            origin=(0.0, 0.0, 0.0),
            width=4.0,
            height=3.0,
            elevation=0.8,
            nx=4,
            ny=3,
        )
    )
    p.jobs.append(
        JobSpec(
            id="j1",
            type="daylight",
            backend="df",
            daylight=DaylightSpec(
                mode="df",
                sky="CIE_overcast",
                external_horizontal_illuminance_lux=10000.0,
                glass_visible_transmittance_default=0.7,
            ),
            targets=["g1"],
        )
    )

    ref = run_job(p, "j1")
    out_dir = Path(ref.result_dir)

    assert (out_dir / "daylight_g1.csv").exists()
    assert (out_dir / "daylight_g1_heatmap.png").exists()
    assert (out_dir / "daylight_summary.json").exists()

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    meta = manifest.get("metadata", {})
    daylight = meta.get("daylight", {})
    assert daylight.get("mode") == "df"
    assert daylight.get("sky") == "CIE_overcast"
    assert float(daylight.get("external_horizontal_illuminance_lux")) == 10000.0
