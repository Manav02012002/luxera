from __future__ import annotations

from pathlib import Path

import pytest

from luxera.cli import main


def test_cli_help_includes_parity_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["parity", "-h"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "run" in out
    assert "update" in out
    assert "report" in out


def test_cli_parity_run_calls_corpus_with_pack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []

    def fake_run_corpus(*, parity_root, selector, baseline, out_dir, update_goldens=False, run_scene=None):  # noqa: ANN001
        calls.append(
            {
                "parity_root": Path(parity_root),
                "selector": selector,
                "baseline": baseline,
                "out_dir": Path(out_dir),
                "update_goldens": update_goldens,
            }
        )
        return {"selected_scenes": 1, "passed": 1, "failed": 0}

    monkeypatch.setattr("luxera.parity.corpus.run_corpus", fake_run_corpus)

    out_dir = tmp_path / "run_out"
    rc = main(["parity", "run", "--pack", "indoor_basic", "--baseline", "luxera", "--out", str(out_dir)])
    assert rc == 0
    assert len(calls) == 1
    call = calls[0]
    assert call["selector"] == {"include_packs": ["indoor_basic"]}
    assert call["baseline"] == "luxera"
    assert call["update_goldens"] is False
    assert call["out_dir"] == out_dir.resolve()


def test_cli_parity_run_selector_yaml_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []

    def fake_run_corpus(*, parity_root, selector, baseline, out_dir, update_goldens=False, run_scene=None):  # noqa: ANN001
        calls.append(selector)
        return {"selected_scenes": 1, "passed": 1, "failed": 0}

    monkeypatch.setattr("luxera.parity.corpus.run_corpus", fake_run_corpus)

    selector = tmp_path / "fast_selection.yaml"
    selector.write_text(
        """
version: 1
name: fast_selection
selectors:
  - kind: pack
    value: indoor_basic
    enabled: true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    rc = main(["parity", "run", "--selector", str(selector), "--baseline", "luxera", "--out", str(tmp_path / "o")])
    assert rc == 0
    assert len(calls) == 1
    assert calls[0].get("include_packs") == ["indoor_basic"]


def test_cli_parity_update_sets_update_goldens(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []

    def fake_run_corpus(*, parity_root, selector, baseline, out_dir, update_goldens=False, run_scene=None):  # noqa: ANN001
        calls.append(update_goldens)
        return {"selected_scenes": 1, "passed": 1, "failed": 0}

    monkeypatch.setattr("luxera.parity.corpus.run_corpus", fake_run_corpus)

    rc = main(
        [
            "parity",
            "update",
            "--pack",
            "indoor_basic",
            "--baseline",
            "luxera",
            "--force",
            "--out",
            str(tmp_path / "u"),
        ]
    )
    assert rc == 0
    assert calls == [True]


def test_cli_parity_update_rejects_non_luxera_baseline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_run_corpus(**kwargs):  # noqa: ANN001, ARG001
        raise AssertionError("run_corpus should not be called")

    monkeypatch.setattr("luxera.parity.corpus.run_corpus", fail_run_corpus)

    rc = main(["parity", "update", "--pack", "indoor_basic", "--baseline", "agi32", "--out", str(tmp_path / "u")])
    assert rc == 2
