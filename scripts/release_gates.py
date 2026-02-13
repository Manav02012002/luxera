from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
import shutil


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode != 0:
        sys.stdout.write(p.stdout)
        sys.stderr.write(p.stderr)
        raise SystemExit(p.returncode)
    return p.stdout


def _radiance_tools_available() -> bool:
    return bool(shutil.which("oconv")) and bool(shutil.which("rtrace"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Run release hardening gates")
    ap.add_argument("--min-bvh-speedup", type=float, default=2.0, help="Minimum acceptable BVH speedup")
    ap.add_argument(
        "--with-radiance-validation",
        action="store_true",
        help="Run radiance-marked validation suite when radiance tools are available.",
    )
    ap.add_argument(
        "--require-radiance-validation",
        action="store_true",
        help="Fail if radiance tools are missing while --with-radiance-validation is requested.",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    print("[gate] core tests")
    _run([sys.executable, "-m", "pytest", "-q", "-m", "not radiance and not gui"])

    print("[gate] explicit gates")
    _run([sys.executable, "-m", "pytest", "-q", "tests/gates/test_gate_determinism.py", "tests/gates/test_gate_agent_approvals.py", "tests/gates/test_gate_failure_recovery.py"])

    print("[gate] artifact/report contracts")
    _run([sys.executable, "-m", "pytest", "-q", "tests/gates/test_report_contract.py", "tests/test_manifest.py"])

    print("[gate] perf budget")
    out = _run([sys.executable, str(root / "benchmarks" / "bench_bvh_occlusion.py")])
    m = re.search(r"Speedup:\s+([0-9.]+)x", out)
    if not m:
        print(out)
        raise SystemExit("Could not parse benchmark speedup")
    speedup = float(m.group(1))
    if speedup < args.min_bvh_speedup:
        raise SystemExit(f"BVH speedup {speedup:.2f}x below threshold {args.min_bvh_speedup:.2f}x")
    print(f"[gate] perf ok: {speedup:.2f}x >= {args.min_bvh_speedup:.2f}x")

    if args.with_radiance_validation:
        print("[gate] radiance validation")
        if not _radiance_tools_available():
            msg = "[gate] radiance validation skipped (missing tools: oconv/rtrace)"
            if args.require_radiance_validation:
                raise SystemExit(msg)
            print(msg)
        else:
            _run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/gates/test_gate_radiance_delta.py",
                    "tests/validation/test_direct_vs_radiance_box.py",
                    "tests/validation/test_direct_vs_radiance_corridor.py",
                    "tests/validation/test_direct_vs_radiance_l_shape.py",
                    "tests/validation/test_direct_vs_radiance_obstructed.py",
                    "tests/validation/test_roadway_luminance.py",
                ]
            )
            print("[gate] radiance validation ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
