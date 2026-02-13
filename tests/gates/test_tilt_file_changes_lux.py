from __future__ import annotations

from pathlib import Path

from luxera.project.runner import run_job_in_memory
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec


def _mk_project(tmp_path: Path, ies_path: Path, name: str) -> Project:
    p = Project(name=name, root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(id="l1", name="L1", photometry_asset_id="a1", transform=TransformSpec(position=(0.0, 0.0, 3.0), rotation=rot))
    )
    p.grids.append(CalcGrid(id="g1", name="g1", origin=(2.0, 0.0, 0.0), width=0.1, height=0.1, elevation=0.0, nx=1, ny=1))
    p.jobs.append(JobSpec(id="j1", type="direct", seed=42))
    return p


def test_tilt_file_changes_lux_reproducibly(tmp_path: Path) -> None:
    src_dir = Path(__file__).resolve().parents[1] / "fixtures" / "ies"
    ies_tilt = tmp_path / "tilt_file_simple.ies"
    ies_none = tmp_path / "tilt_none.ies"
    tilt_dat = tmp_path / "tilt.dat"
    ies_tilt.write_text((src_dir / "tilt_file_simple.ies").read_text(encoding="utf-8"), encoding="utf-8")
    tilt_dat.write_text((src_dir / "tilt.dat").read_text(encoding="utf-8"), encoding="utf-8")
    ies_none.write_text(
        (src_dir / "tilt_file_simple.ies").read_text(encoding="utf-8").replace("TILT=FILE tilt.dat", "TILT=NONE"),
        encoding="utf-8",
    )

    p_none = _mk_project(tmp_path, ies_none, "NoTilt")
    p_tilt = _mk_project(tmp_path, ies_tilt, "TiltFile")

    e_none = float(run_job_in_memory(p_none, "j1").summary.get("mean_lux", 0.0))
    e_tilt_1 = float(run_job_in_memory(p_tilt, "j1").summary.get("mean_lux", 0.0))
    e_tilt_2 = float(run_job_in_memory(p_tilt, "j1").summary.get("mean_lux", 0.0))

    assert e_none > 0.0
    assert e_tilt_1 > 0.0
    assert e_tilt_1 < e_none
    assert e_tilt_1 == e_tilt_2
