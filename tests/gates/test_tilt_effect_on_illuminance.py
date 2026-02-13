from __future__ import annotations

from pathlib import Path

from luxera.project.io import save_project_schema
from luxera.project.runner import run_job_in_memory
from luxera.project.schema import CalcGrid, JobSpec, LuminaireInstance, PhotometryAsset, Project, RotationSpec, TransformSpec


def _ies_none(path: Path) -> Path:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 30 60
0
1000 1000 1000
""",
        encoding="utf-8",
    )
    return path


def _ies_tilt(path: Path) -> Path:
    src = Path(__file__).resolve().parents[1] / "fixtures" / "ies" / "tilt_include_simple.ies"
    path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def _mk(tmp_path: Path, ies: Path, name: str) -> float:
    p = Project(name=name, root_dir=str(tmp_path))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(id="l1", name="L1", photometry_asset_id="a1", transform=TransformSpec(position=(0.0, 0.0, 3.0), rotation=rot))
    )
    p.grids.append(CalcGrid(id="g1", name="g1", origin=(2.0, 0.0, 0.0), width=0.1, height=0.1, elevation=0.0, nx=1, ny=1))
    p.jobs.append(JobSpec(id="j1", type="direct"))
    ref = run_job_in_memory(p, "j1")
    return float(ref.summary.get("mean_lux", 0.0))


def test_tilt_include_changes_result(tmp_path: Path) -> None:
    e_none = _mk(tmp_path, _ies_none(tmp_path / "n.ies"), "NoTilt")
    e_tilt = _mk(tmp_path, _ies_tilt(tmp_path / "t.ies"), "Tilt")
    assert e_none > 0.0
    assert e_tilt > 0.0
    assert e_tilt < e_none
