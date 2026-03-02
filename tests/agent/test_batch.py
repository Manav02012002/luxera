from __future__ import annotations

import json
from pathlib import Path

import pytest

from luxera.agent.batch import BatchRunner, BatchStep


class _FakeRuntimeResult:
    def __init__(self, *, warnings=None, artifacts=None):
        self.warnings = list(warnings or [])
        self.produced_artifacts = list(artifacts or [])
        self.run_manifest = {}


class _FakeRuntime:
    def __init__(self, scripted=None):
        self._scripted = list(scripted or [])
        self.calls = []

    def execute(self, project_path, intent, approvals=None):
        self.calls.append({"project_path": project_path, "intent": intent, "approvals": dict(approvals or {})})
        if self._scripted:
            item = self._scripted.pop(0)
            if isinstance(item, Exception):
                raise item
            if isinstance(item, dict):
                if item.get("raise"):
                    raise RuntimeError(str(item["raise"]))
                return _FakeRuntimeResult(warnings=item.get("warnings", []), artifacts=item.get("artifacts", []))
        return _FakeRuntimeResult()


def test_batch_from_steps_list(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeRuntime(scripted=[{}, {}, {}])
    monkeypatch.setattr("luxera.agent.batch.AgentRuntime", lambda: fake)

    runner = BatchRunner(project_path="proj.luxera", output_dir=tmp_path)
    steps = [BatchStep("a"), BatchStep("b"), BatchStep("c")]
    res = runner.run_steps(steps)

    assert len(res) == 3
    assert all(r.success for r in res)


def test_batch_fail_on_error_stops(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeRuntime(scripted=[{}, RuntimeError("boom"), {}])
    monkeypatch.setattr("luxera.agent.batch.AgentRuntime", lambda: fake)

    runner = BatchRunner(project_path="proj.luxera", output_dir=tmp_path)
    steps = [BatchStep("ok"), BatchStep("fail", fail_on_error=True), BatchStep("never")]
    res = runner.run_steps(steps)

    assert len(res) == 2
    assert res[0].success is True
    assert res[1].success is False


def test_batch_from_file(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeRuntime(scripted=[{}, {}])
    monkeypatch.setattr("luxera.agent.batch.AgentRuntime", lambda: fake)

    batch_file = tmp_path / "batch.json"
    batch_file.write_text(
        json.dumps(
            {
                "project": "proj.luxera",
                "output": str(tmp_path / "out"),
                "steps": [{"intent": "import office.dxf"}, {"intent": "run calc"}],
            }
        ),
        encoding="utf-8",
    )

    runner = BatchRunner(project_path="placeholder.luxera", output_dir=tmp_path / "placeholder_out")
    res = runner.run_from_file(batch_file)

    assert len(res) == 2
    assert all(r.success for r in res)


def test_batch_summary(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeRuntime(scripted=[{}, RuntimeError("boom")])
    monkeypatch.setattr("luxera.agent.batch.AgentRuntime", lambda: fake)

    runner = BatchRunner(project_path="proj.luxera", output_dir=tmp_path)
    results = runner.run_steps([BatchStep("ok"), BatchStep("bad", fail_on_error=False)])
    summary = runner.generate_summary(results)

    assert "Passed:" in summary
    assert "Failed:" in summary


def test_batch_approve_all(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeRuntime(scripted=[{}])
    monkeypatch.setattr("luxera.agent.batch.AgentRuntime", lambda: fake)

    runner = BatchRunner(project_path="proj.luxera", output_dir=tmp_path)
    _ = runner.run_steps([BatchStep("run calc", approve_all=True)])

    assert fake.calls
    approvals = fake.calls[0]["approvals"]
    assert approvals.get("apply_diff") is True
    assert approvals.get("run_job") is True
