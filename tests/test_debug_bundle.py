from pathlib import Path
import zipfile

from luxera.export.debug_bundle import export_debug_bundle
from luxera.project.schema import Project, JobResultRef


def test_export_debug_bundle(tmp_path: Path):
    project = Project(name="Test", root_dir=str(tmp_path))
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    (result_dir / "result.json").write_text("{}", encoding="utf-8")

    ref = JobResultRef(job_id="job1", job_hash="hash1", result_dir=str(result_dir))
    out = export_debug_bundle(project, ref, tmp_path / "bundle.zip")

    assert out.exists()
    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
        assert "result.json" in names
