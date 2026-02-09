from pathlib import Path
import json

from luxera.backends import radiance as rad
from luxera.project.schema import (
    Project,
    PhotometryAsset,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    TransformSpec,
    RotationSpec,
)


def test_gate_radiance_delta_thresholds(monkeypatch, tmp_path: Path):
    ies_path = tmp_path / "fixture.ies"
    ies_path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1000 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
100 80 60
""",
        encoding="utf-8",
    )

    project = Project(name="RadGate")
    project.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies_path)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    project.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="L1",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(0.0, 0.0, 3.0), rotation=rot),
        )
    )
    project.grids.append(CalcGrid(id="g1", name="g", origin=(0.0, 0.0, 0.0), width=1.0, height=1.0, elevation=0.8, nx=2, ny=2))
    # Lenient thresholds for mock path.
    job = JobSpec(
        id="j1",
        type="direct",
        backend="radiance",
        settings={"radiance_max_mean_rel_error": 10.0, "radiance_max_abs_lux_error": 10000.0},
    )

    monkeypatch.setattr(rad.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    def fake_check_call(cmd, stdout=None, stderr=None):  # noqa: ARG001
        if stdout is not None:
            stdout.write(b"OCT")
        return 0

    def fake_check_output(cmd, stderr=None, text=False, input=None):  # noqa: ARG001
        if "-version" in cmd:
            return "rtrace 5.4a"
        payload = b"0.10 0.20 0.30\n0.10 0.20 0.30\n0.10 0.20 0.30\n0.10 0.20 0.30\n"
        if text:
            return payload.decode("utf-8")
        return payload

    monkeypatch.setattr(rad.subprocess, "check_call", fake_check_call)
    monkeypatch.setattr(rad.subprocess, "check_output", fake_check_output)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = rad.run_radiance_direct(project, job, out_dir)
    assert result.summary["backend_comparison_pass"] is True

    report = json.loads((out_dir / "backend_comparison.json").read_text(encoding="utf-8"))
    assert report["pass"] is True
