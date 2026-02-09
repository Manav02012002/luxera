from pathlib import Path
import json

from luxera.cli import main
from luxera.project.schema import Project, JobResultRef
from luxera.project.io import save_project_schema


def test_cli_compare_results(tmp_path: Path):
    r1 = tmp_path / "r1"
    r2 = tmp_path / "r2"
    r1.mkdir()
    r2.mkdir()
    (r1 / "result.json").write_text(json.dumps({"summary": {"mean_lux": 100.0}}), encoding="utf-8")
    (r2 / "result.json").write_text(json.dumps({"summary": {"mean_lux": 125.0}}), encoding="utf-8")
    p = Project(name="cmp", root_dir=str(tmp_path))
    p.results.append(JobResultRef(job_id="j1", job_hash="h1", result_dir=str(r1)))
    p.results.append(JobResultRef(job_id="j2", job_hash="h2", result_dir=str(r2)))
    proj = tmp_path / "p.json"
    save_project_schema(p, proj)

    out = tmp_path / "cmp.json"
    rc = main(["compare-results", str(proj), "j1", "j2", "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["delta"]["mean_lux"]["delta"] == 25.0
