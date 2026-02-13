from __future__ import annotations

from pathlib import Path

from luxera.agent.skills.compliance import build_compliance_skill
from luxera.project.io import save_project_schema
from luxera.project.schema import JobResultRef, JobSpec, Project


def test_compliance_explanations_include_actual_and_threshold_values(tmp_path: Path) -> None:
    p = Project(name="ComplianceExplain", root_dir=str(tmp_path))
    p.jobs.append(JobSpec(id="j1", type="direct", backend="cpu", settings={}))
    p.results.append(
        JobResultRef(
            job_id="j1",
            job_hash="h1",
            result_dir=str(tmp_path / "results" / "j1"),
            summary={
                "compliance_profile": {
                    "status": "FAIL",
                    "avg_ok": False,
                    "avg_lux": 320.0,
                    "target_avg_lux": 500.0,
                    "uniformity_ok": False,
                    "uniformity": 0.45,
                    "uniformity_min": 0.60,
                }
            },
        )
    )
    project_path = tmp_path / "project.json"
    save_project_schema(p, project_path)

    out = build_compliance_skill(str(project_path), domain="indoor", ensure_run=False)

    explanations = out.run_manifest.get("explanations")
    assert isinstance(explanations, list)
    assert explanations
    joined = "\n".join(str(x) for x in explanations)
    assert "avg_ok failed" in joined
    assert "actual=320.000" in joined
    assert "threshold >= 500.000" in joined
    assert "uniformity_ok failed" in joined
    assert "actual=0.450" in joined
    assert "threshold >= 0.600" in joined
