from __future__ import annotations

import sys

import pytest

from scripts import benchmark_gates


def test_benchmark_gates_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> str:
        calls.append(cmd)
        if "bench_bvh_occlusion.py" in " ".join(cmd):
            return "Speedup:    2.40x\n"
        return "second_run_s: 5.1000\n"

    monkeypatch.setattr(benchmark_gates, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["benchmark_gates.py"])

    assert benchmark_gates.main() == 0
    assert any("bench_bvh_occlusion.py" in " ".join(c) for c in calls)
    assert any("bench_occlusion.py" in " ".join(c) for c in calls)


def test_benchmark_gates_fails_on_speedup(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str]) -> str:
        if "bench_bvh_occlusion.py" in " ".join(cmd):
            return "Speedup: 1.20x"
        return "second_run_s: 3.0"

    monkeypatch.setattr(benchmark_gates, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["benchmark_gates.py", "--min-bvh-speedup", "2.0"])

    with pytest.raises(SystemExit):
        benchmark_gates.main()


def test_benchmark_gates_fails_on_occlusion_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str]) -> str:
        if "bench_bvh_occlusion.py" in " ".join(cmd):
            return "Speedup: 3.00x"
        return "second_run_s: 99.0"

    monkeypatch.setattr(benchmark_gates, "_run", fake_run)
    monkeypatch.setattr(sys, "argv", ["benchmark_gates.py", "--max-occlusion-second-run-s", "20.0"])

    with pytest.raises(SystemExit):
        benchmark_gates.main()
