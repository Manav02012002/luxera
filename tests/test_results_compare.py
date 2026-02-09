from pathlib import Path
import json

from luxera.results.compare import compare_job_results
from luxera.project.schema import Project, JobResultRef


def test_compare_job_results(tmp_path: Path):
    r1 = tmp_path / "r1"
    r2 = tmp_path / "r2"
    r1.mkdir()
    r2.mkdir()
    (r1 / "result.json").write_text(json.dumps({"summary": {"mean_lux": 100.0, "max_lux": 200.0}}), encoding="utf-8")
    (r2 / "result.json").write_text(json.dumps({"summary": {"mean_lux": 120.0, "max_lux": 220.0}}), encoding="utf-8")
    p = Project(name="cmp")
    p.results.append(JobResultRef(job_id="a", job_hash="ha", result_dir=str(r1)))
    p.results.append(JobResultRef(job_id="b", job_hash="hb", result_dir=str(r2)))
    cmp = compare_job_results(p, "a", "b")
    assert cmp["delta"]["mean_lux"]["delta"] == 20.0
