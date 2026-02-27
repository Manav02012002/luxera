from __future__ import annotations

import json
from pathlib import Path

from luxera.project.io import load_project_schema
from luxera.project.runner import run_job_in_memory


def test_auto_wall_vertical_planes_generation_and_user_plane_present(tmp_path: Path) -> None:
    pack_dir = Path(__file__).parent / "golden" / "indoor_multiplane_office"
    src = pack_dir / "office_project.json"
    p = load_project_schema(src)
    p.root_dir = str(pack_dir)

    ref = run_job_in_memory(p, "j1")
    payload = json.loads((Path(ref.result_dir) / "result.json").read_text(encoding="utf-8"))
    indoor = payload.get("summary", {}).get("indoor_planes", {})
    per_plane = indoor.get("per_plane", []) if isinstance(indoor, dict) else []

    auto_walls = [r for r in per_plane if isinstance(r, dict) and r.get("source") == "auto_wall"]
    user_vertical = [r for r in per_plane if isinstance(r, dict) and r.get("id") == "vp_user"]

    assert len(auto_walls) >= 4
    assert len(user_vertical) == 1


def test_golden_office_pack_expected_ranges_and_uniformity() -> None:
    pack_dir = Path(__file__).parent / "golden" / "indoor_multiplane_office"
    expected = json.loads((pack_dir / "expected.json").read_text(encoding="utf-8"))

    p = load_project_schema(pack_dir / "office_project.json")
    p.root_dir = str(pack_dir)
    ref = run_job_in_memory(p, "j1")
    payload = json.loads((Path(ref.result_dir) / "result.json").read_text(encoding="utf-8"))

    summary = payload.get("summary", {})
    indoor = summary.get("indoor_planes", {}) if isinstance(summary, dict) else {}
    per_plane = indoor.get("per_plane", []) if isinstance(indoor, dict) else []
    cyl = indoor.get("cylindrical", []) if isinstance(indoor, dict) else []

    work = next(r for r in per_plane if isinstance(r, dict) and r.get("source") == "workplane")
    lo, hi = expected["workplane"]["Eavg_range"]
    assert lo <= float(work["Eavg"]) <= hi
    assert float(work["U0"]) >= float(expected["workplane"]["U0_min"])

    vertical = [
        r
        for r in per_plane
        if isinstance(r, dict) and (str(r.get("source", "")).endswith("wall") or r.get("source") == "user_defined")
    ]
    assert len(vertical) >= int(expected["vertical_min_count"])

    assert cyl
    c0 = cyl[0]
    clo, chi = expected["cylindrical"]["Eavg_range"]
    assert clo <= float(c0["Eavg"]) <= chi
    assert float(c0["U0"]) >= float(expected["cylindrical"]["U0_min"])
    assert float(indoor.get("maintenance_factor", 1.0)) == 0.8
