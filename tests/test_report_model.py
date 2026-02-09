import json
from pathlib import Path

from luxera.export.report_model import build_en13032_report_model
from luxera.project.schema import Project, JobResultRef, PhotometryAsset


def test_report_model_build(tmp_path: Path):
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "job_hash": "hash1",
                "job": {"id": "job1", "type": "direct"},
                "summary": {"mean_lux": 500},
                "assets": {"asset1": "h1"},
                "solver": {"package_version": "0.2.0"},
            }
        ),
        encoding="utf-8",
    )

    project = Project(name="Test")
    project.photometry_assets.append(
        PhotometryAsset(id="asset1", format="IES", path="/tmp/a.ies", content_hash="h1", metadata={"filename": "a.ies"})
    )

    ref = JobResultRef(job_id="job1", job_hash="hash1", result_dir=str(result_dir))
    model = build_en13032_report_model(project, ref)

    assert model.audit.job_id == "job1"
    assert model.audit.job_hash == "hash1"
    assert model.photometry[0].asset_id == "asset1"
    assert model.summary["mean_lux"] == 500
    assert "rooms" in model.geometry
    assert "job" in model.method
