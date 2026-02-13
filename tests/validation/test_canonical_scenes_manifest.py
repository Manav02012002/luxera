from __future__ import annotations

import json
from pathlib import Path

from luxera.project.io import load_project_schema


def test_canonical_scene_library_contract() -> None:
    root = Path(__file__).resolve().parent / "scenes"
    expected = {"box_room", "corridor", "l_shape", "obstructed", "occlusion_edge", "tilt_effect"}
    found = {p.name for p in root.iterdir() if p.is_dir()}
    assert expected.issubset(found)

    for scene_name in sorted(expected):
        scene_dir = root / scene_name
        project_path = scene_dir / "project.json"
        invariance_path = scene_dir / "expected_invariances.json"
        tolerance_path = scene_dir / "tolerance_band.json"
        assert project_path.exists()
        assert invariance_path.exists()
        assert tolerance_path.exists()

        project = load_project_schema(project_path)
        assert project.jobs
        assert project.photometry_assets

        invariances = json.loads(invariance_path.read_text(encoding="utf-8"))
        assert "translation_invariance" in invariances
        assert "scale_invariance_units" in invariances
        if scene_name == "tilt_effect":
            assert isinstance(invariances.get("tilt_file_vs_none"), dict)

        tolerance = json.loads(tolerance_path.read_text(encoding="utf-8"))
        assert float(tolerance["mean_rel_error_max"]) > 0.0
        assert float(tolerance["mean_abs_error_max_lux"]) > 0.0
