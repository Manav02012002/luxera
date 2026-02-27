from __future__ import annotations

import json
from pathlib import Path

import pytest

from luxera.project.io import load_project_schema
from luxera.project.runner import RunnerError, run_job_in_memory
from luxera.standards.roadway import evaluate_roadway_profile, get_profile, list_profiles


def test_roadway_profile_table_lookup() -> None:
    profiles = list_profiles()
    ids = {p.id for p in profiles}
    assert "en13201_m3_common" in ids
    assert "demo_nonstandard_placeholder" in ids
    p = get_profile("en13201_m3_common")
    assert p.roadway_class == "M3"
    assert p.requirements
    metrics = {r.metric for r in p.requirements}
    assert {"mean_lux", "uniformity_ratio", "ul_longitudinal", "road_luminance_mean_cd_m2"}.issubset(metrics)


def test_roadway_profile_missing_profile_error() -> None:
    with pytest.raises(KeyError):
        get_profile("missing_profile_does_not_exist")


def test_roadway_profile_evaluate_margins() -> None:
    p = get_profile("en13201_m3_common")
    summary = {
        "mean_lux": 2.0,
        "uniformity_ratio": 0.2,
        "ul_longitudinal": 0.3,
        "road_luminance_mean_cd_m2": 0.4,
        "threshold_increment_ti_proxy_percent": 12.0,
        "surround_ratio_proxy": 0.7,
    }
    compliance, submission = evaluate_roadway_profile(p, summary)
    assert compliance["status"] == "FAIL"
    assert compliance["avg_ok"] is True
    assert compliance["uo_ok"] is False
    assert compliance["margins"]["uniformity_ratio"] < 0.0
    assert submission["status"] == "FAIL"
    assert isinstance(submission.get("checks"), list)


def test_roadway_profile_selected_from_scene_roadway_field() -> None:
    scene = Path("luxera/scenes/refs/roadway_profile_check_pack/scene.lux.json")
    project = load_project_schema(scene)
    project.root_dir = str(scene.parent)
    ref = run_job_in_memory(project, "job_roadway_cpu")
    summary = ref.summary
    prof = summary.get("roadway_profile", {})
    assert prof.get("id") == "demo_nonstandard_placeholder"
    comp = summary.get("compliance", {})
    assert comp.get("profile_id") == "demo_nonstandard_placeholder"


def test_roadway_profile_missing_in_scene_raises_error() -> None:
    scene = Path("luxera/scenes/refs/roadway_profile_check_pack/scene.lux.json")
    project = load_project_schema(scene)
    project.root_dir = str(scene.parent)
    assert project.roadways
    project.roadways[0].profile = "missing_profile_does_not_exist"
    with pytest.raises(RunnerError):
        run_job_in_memory(project, "job_roadway_cpu")


def test_roadway_profile_golden_pack(tmp_path: Path) -> None:
    pack = Path("luxera/scenes/refs/roadway_profile_m3")
    expected = json.loads((pack / "expected" / "expected.json").read_text(encoding="utf-8"))
    scene = pack / "scene.lux.json"
    project = load_project_schema(scene)
    project.root_dir = str(pack)

    ref = run_job_in_memory(project, "job_roadway_profile")
    summary = ref.summary

    tol = float(expected["tolerance_abs"])
    prof = summary.get("roadway_profile", {})
    assert prof.get("id") == expected["profile"]["id"]
    assert prof.get("class") == expected["profile"]["class"]

    comp = summary.get("compliance", {})
    for k, v in expected["compliance"].items():
        assert comp.get(k) == v

    margins = comp.get("margins", {})
    for k, v in expected["margins"].items():
        assert float(margins.get(k, 0.0)) == pytest.approx(float(v), abs=tol)

    out_dir = Path(ref.result_dir)
    assert (out_dir / "roadway_submission.json").exists()
    assert (out_dir / "roadway_submission.md").exists()
