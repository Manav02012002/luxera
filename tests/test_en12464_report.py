import json
from pathlib import Path

from luxera.export.en12464_report import build_en12464_report_model
from luxera.export.en12464_pdf import render_en12464_pdf
from luxera.export.en12464_html import render_en12464_html
from luxera.project.schema import Project, JobResultRef


def test_en12464_report_outputs(tmp_path: Path):
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    (result_dir / "result.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "job_hash": "hash1",
                "job": {"id": "job1", "type": "direct"},
                "summary": {"compliance": {"status": "PASS"}},
                "assets": {},
                "solver": {"package_version": "0.2.0"},
            }
        ),
        encoding="utf-8",
    )

    project = Project(name="Test")
    ref = JobResultRef(job_id="job1", job_hash="hash1", result_dir=str(result_dir))
    model = build_en12464_report_model(project, ref)

    pdf = render_en12464_pdf(model, tmp_path / "en12464.pdf")
    html = render_en12464_html(model, tmp_path / "en12464.html")

    assert pdf.exists()
    assert html.exists()
    assert pdf.stat().st_size > 0
    assert html.stat().st_size > 0
