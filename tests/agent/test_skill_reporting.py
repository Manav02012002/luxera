from __future__ import annotations

import shutil
from pathlib import Path

from luxera.agent.skills.reporting import build_reporting_skill


def test_skill_reporting_exports(tmp_path: Path) -> None:
    src = Path("examples/indoor_office").resolve()
    dst = tmp_path / "indoor_office"
    shutil.copytree(src, dst)
    project_path = dst / "office.luxera.json"

    out = build_reporting_skill(str(project_path), job_id="office_direct", template="en12464", ensure_run=True)
    assert Path(out.artifacts["report"]).exists()
    assert Path(out.artifacts["audit_bundle"]).exists()
