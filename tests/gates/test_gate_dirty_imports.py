from __future__ import annotations

import json
from pathlib import Path

import pytest

from luxera.io.import_pipeline import run_import_pipeline


CASE_DIR = Path("tests/assets/geometry_cases").resolve()
ROOT = Path(__file__).resolve().parents[2]


def _dirty_cases() -> list[Path]:
    return sorted(CASE_DIR.glob("dirty_import_*.json"))


@pytest.mark.parametrize("case_path", _dirty_cases(), ids=lambda p: p.stem)
def test_gate_dirty_imports(case_path: Path) -> None:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    src = (ROOT / str(case["path"])).resolve()
    res = run_import_pipeline(str(src), fmt=str(case["fmt"]))

    assert res.geometry is not None
    assert all(s.status != "error" for s in res.report.stages)

    stages = {s.name: s for s in res.report.stages}
    for name in case["expect"].get("required_stages", []):
        assert name in stages
        assert stages[name].status == "ok"

    min_rooms = int(case["expect"].get("min_rooms", 0))
    if min_rooms > 0:
        assert len(res.geometry.rooms) >= min_rooms

    if bool(case["expect"].get("require_scene_health_counts", False)):
        counts = res.report.scene_health.get("counts", {}) if isinstance(res.report.scene_health, dict) else {}
        assert isinstance(counts, dict)
        key = str(case["expect"].get("require_scene_health_key", ""))
        assert key in counts

    block_instances_min = case["expect"].get("raw_import_block_instances_min")
    if block_instances_min is not None:
        raw = stages["RawImport"].details
        got = int(raw.get("block_instances", 0)) if isinstance(raw, dict) else 0
        assert got >= int(block_instances_min)
