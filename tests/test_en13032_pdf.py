from pathlib import Path

from luxera.export.en13032_pdf import render_en13032_pdf
from luxera.export.report_model import EN13032ReportModel, AuditHeader, PhotometryEntry


def test_en13032_pdf_render(tmp_path: Path):
    model = EN13032ReportModel(
        audit=AuditHeader(
            project_name="Test",
            schema_version=1,
            job_id="job1",
            job_hash="hash1",
            solver={"package_version": "0.2.0", "git_commit": "abc"},
            settings={},
            asset_hashes={},
        ),
        photometry=[
            PhotometryEntry(asset_id="a1", format="IES", filename="a.ies", content_hash="h1", metadata={})
        ],
        summary={"mean_lux": 500},
        geometry={"rooms": [], "grids": []},
        method={"job": {"type": "direct"}, "solver": {"package_version": "0.2.0"}},
        compliance={"status": "PASS"},
    )

    out = render_en13032_pdf(model, tmp_path / "report.pdf")
    assert out.exists()
    assert out.stat().st_size > 0
