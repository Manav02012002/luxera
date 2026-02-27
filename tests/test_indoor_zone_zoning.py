from __future__ import annotations

import json
from pathlib import Path

from luxera.project.io import load_project_schema
from luxera.project.runner import run_job_in_memory


def test_golden_two_zone_pack_metrics_and_compliance() -> None:
    pack_dir = Path(__file__).parent / "golden" / "indoor_zones_twoarea"
    expected = json.loads((pack_dir / "expected.json").read_text(encoding="utf-8"))

    p = load_project_schema(pack_dir / "office_project.json")
    p.root_dir = str(pack_dir)
    ref = run_job_in_memory(p, "j1")

    payload = json.loads((Path(ref.result_dir) / "result.json").read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    zone_rows = summary.get("zone_metrics", []) if isinstance(summary, dict) else []

    assert [str(r.get("zone_id")) for r in zone_rows if isinstance(r, dict)] == expected["ordering"]

    by_id = {str(r.get("zone_id")): r for r in zone_rows if isinstance(r, dict)}
    for zone_id, erow in expected["zones"].items():
        row = by_id[zone_id]
        lo, hi = erow["Eavg_range"]
        assert lo <= float(row["Eavg"]) <= hi
        assert float(row["U0"]) >= float(erow["U0_min"])
        assert str(row["status"]) == str(erow["status"])

    assert float(by_id["zone_task"]["Eavg"]) > float(by_id["zone_surround"]["Eavg"])

    tables = json.loads((Path(ref.result_dir) / "tables.json").read_text(encoding="utf-8"))
    zone_table = tables.get("zones", []) if isinstance(tables, dict) else []
    assert isinstance(zone_table, list)
    assert len(zone_table) == 2
