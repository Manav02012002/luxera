from __future__ import annotations

import json
from pathlib import Path

from luxera.parity.corpus import run_corpus
from luxera.parity.invariance import InvarianceMismatch, InvarianceResult


def _write_pack(root: Path, *, invariance: bool = False) -> Path:
    pack_dir = root / "packs" / "indoor_basic"
    (pack_dir / "scenes").mkdir(parents=True, exist_ok=True)
    (pack_dir / "expected" / "luxera" / "v1").mkdir(parents=True, exist_ok=True)

    inv_line = "  invariance: true\n" if invariance else ""
    (pack_dir / "pack.yaml").write_text(
        f"""
id: indoor_basic
title: Indoor Basic
version: 1
engines:
  - job_direct_cpu
scenes:
  - id: office_01
    path: scenes/office_01.lux.json
    tags: [indoor, fast]
global:
  random_seed: 42
  deterministic: true
{inv_line}""".strip()
        + "\n",
        encoding="utf-8",
    )
    return pack_dir


def test_run_corpus_with_stub_scene_runner_pass(tmp_path: Path) -> None:
    parity_root = tmp_path / "parity"
    pack_dir = _write_pack(parity_root)

    expected = {
        "schema_version": "parity_expected_v2",
        "scene_id": "office_01",
        "baseline": "luxera",
        "baseline_version": "v1",
        "results": {"mean_lux": 100.0},
        "tags": ["indoor"],
    }
    exp_path = pack_dir / "expected" / "luxera" / "v1" / "office_01.expected.json"
    exp_path.write_text(json.dumps(expected, indent=2, sort_keys=True), encoding="utf-8")

    def stub_run_scene(scene_path: Path):
        assert scene_path.name == "office_01.lux.json"
        return {"results": {"mean_lux": 100.0}}

    out = tmp_path / "out"
    summary = run_corpus(
        parity_root=parity_root,
        selector={"include_packs": ["indoor_basic"]},
        baseline="luxera",
        out_dir=out,
        update_goldens=False,
        run_scene=stub_run_scene,
    )

    assert summary["selected_scenes"] == 1
    assert summary["passed"] == 1
    assert summary["failed"] == 0
    assert (out / "summary.json").exists()
    assert (out / "summary.md").exists()


def test_run_corpus_writes_fail_artifacts_and_can_update_goldens(tmp_path: Path) -> None:
    parity_root = tmp_path / "parity"
    _write_pack(parity_root)

    def stub_run_scene(_scene_path: Path):
        return {
            "schema_version": "parity_expected_v2",
            "scene_id": "office_01",
            "baseline": "luxera",
            "baseline_version": "v1",
            "results": {"mean_lux": 55.0},
            "tags": ["indoor", "fast"],
        }

    out_fail = tmp_path / "out_fail"
    summary_fail = run_corpus(
        parity_root=parity_root,
        selector={"include_scene_ids": ["office_01"]},
        baseline="luxera",
        out_dir=out_fail,
        update_goldens=False,
        run_scene=stub_run_scene,
    )
    assert summary_fail["failed"] == 1
    assert (out_fail / "failures" / "office_01" / "diff.json").exists()
    assert (out_fail / "failures" / "office_01" / "actual.json").exists()
    assert (out_fail / "failures" / "office_01" / "expected.json").exists()

    out_update = tmp_path / "out_update"
    summary_update = run_corpus(
        parity_root=parity_root,
        selector={"include_scene_ids": ["office_01"]},
        baseline="luxera",
        out_dir=out_update,
        update_goldens=True,
        run_scene=stub_run_scene,
    )
    assert summary_update["failed"] == 0
    exp_path = parity_root / "packs" / "indoor_basic" / "expected" / "luxera" / "v1" / "office_01.expected.json"
    assert exp_path.exists()
    updates_log = out_update / "golden_updates.json"
    assert updates_log.exists()
    payload = json.loads(updates_log.read_text(encoding="utf-8"))
    assert payload.get("baseline") == "luxera"
    updated = payload.get("updated")
    assert isinstance(updated, list) and len(updated) == 1
    row = updated[0]
    assert row.get("scene_id") == "office_01"
    assert row.get("new_hash", "").startswith("sha256:")


def test_run_corpus_run_mode_never_writes_expected(tmp_path: Path) -> None:
    parity_root = tmp_path / "parity"
    pack_dir = _write_pack(parity_root)
    expected_path = pack_dir / "expected" / "luxera" / "v1" / "office_01.expected.json"
    expected_path.write_text(
        json.dumps(
            {
                "schema_version": "parity_expected_v2",
                "scene_id": "office_01",
                "baseline": "luxera",
                "baseline_version": "v1",
                "results": {"mean_lux": 1.0},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    before = expected_path.read_text(encoding="utf-8")

    def stub_run_scene(_scene_path: Path):
        return {"results": {"mean_lux": 2.0}}

    out_dir = tmp_path / "out_run"
    summary = run_corpus(
        parity_root=parity_root,
        selector={"include_scene_ids": ["office_01"]},
        baseline="luxera",
        out_dir=out_dir,
        update_goldens=False,
        run_scene=stub_run_scene,
    )
    assert summary["failed"] == 1
    after = expected_path.read_text(encoding="utf-8")
    assert after == before


def test_run_corpus_fails_when_invariance_mismatch_detected(tmp_path: Path, monkeypatch) -> None:
    parity_root = tmp_path / "parity"
    pack_dir = _write_pack(parity_root, invariance=True)

    expected = {
        "schema_version": "parity_expected_v2",
        "scene_id": "office_01",
        "baseline": "luxera",
        "baseline_version": "v1",
        "results": {"mean_lux": 100.0},
        "tags": ["indoor"],
    }
    exp_path = pack_dir / "expected" / "luxera" / "v1" / "office_01.expected.json"
    exp_path.write_text(json.dumps(expected, indent=2, sort_keys=True), encoding="utf-8")

    def stub_run_scene(_scene_path: Path):
        return {"results": {"mean_lux": 100.0}}

    def fake_invariance(*args, **kwargs):  # noqa: ANN001
        return InvarianceResult(
            passed=False,
            transforms_checked=3,
            mismatches=[
                InvarianceMismatch(
                    transform="rotate_z_90",
                    metric="E_avg",
                    baseline=100.0,
                    variant=101.0,
                    abs_error=1.0,
                    rel_error=0.01,
                    abs_tol=1e-4,
                    rel_tol=1e-5,
                    reason="scalar_tolerance_exceeded",
                )
            ],
            details={"transforms": {"rotate_z_90": {"failures": ["x"]}}},
        )

    monkeypatch.setattr("luxera.parity.corpus.run_invariance_for_scene", fake_invariance)

    out = tmp_path / "out_inv_fail"
    summary = run_corpus(
        parity_root=parity_root,
        selector={"include_packs": ["indoor_basic"]},
        baseline="luxera",
        out_dir=out,
        update_goldens=False,
        run_scene=stub_run_scene,
    )
    assert summary["failed"] == 1
    assert summary["scenes"][0]["invariance_failures"] == 1
    md = (out / "summary.md").read_text(encoding="utf-8")
    assert "rotate_z_90" in md
