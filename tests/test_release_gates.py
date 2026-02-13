from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import release_gates  # noqa: E402


def test_release_gates_radiance_skips_when_tools_missing(monkeypatch) -> None:
    calls = []

    def fake_run(cmd):  # noqa: ANN001
        calls.append(cmd)
        if "bench_bvh_occlusion.py" in " ".join(cmd):
            return "Speedup: 3.0x"
        return ""

    monkeypatch.setattr(release_gates, "_run", fake_run)
    monkeypatch.setattr(release_gates.shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "argv", ["release_gates.py", "--with-radiance-validation"])

    assert release_gates.main() == 0
    assert any("bench_bvh_occlusion.py" in " ".join(c) for c in calls)
    # No explicit radiance pytest invocation when missing tools.
    assert not any("test_direct_vs_radiance_l_shape.py" in " ".join(c) for c in calls)


def test_release_gates_radiance_required_fails_when_tools_missing(monkeypatch) -> None:
    def fake_run(cmd):  # noqa: ANN001
        if "bench_bvh_occlusion.py" in " ".join(cmd):
            return "Speedup: 3.0x"
        return ""

    monkeypatch.setattr(release_gates, "_run", fake_run)
    monkeypatch.setattr(release_gates.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["release_gates.py", "--with-radiance-validation", "--require-radiance-validation"],
    )

    with pytest.raises(SystemExit):
        release_gates.main()


def test_release_gates_radiance_runs_when_tools_present(monkeypatch) -> None:
    calls = []

    def fake_run(cmd):  # noqa: ANN001
        calls.append(cmd)
        if "bench_bvh_occlusion.py" in " ".join(cmd):
            return "Speedup: 3.0x"
        return ""

    monkeypatch.setattr(release_gates, "_run", fake_run)
    monkeypatch.setattr(release_gates.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(sys, "argv", ["release_gates.py", "--with-radiance-validation"])

    assert release_gates.main() == 0
    rad_calls = [c for c in calls if "test_direct_vs_radiance_l_shape.py" in " ".join(c)]
    assert rad_calls, "expected radiance validation call to include new scene tests"
