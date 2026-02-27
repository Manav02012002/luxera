from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


SPEEDUP_RE = re.compile(r"Speedup:\s+([0-9.]+)x")
SECOND_RUN_RE = re.compile(r"second_run_s:\s*([0-9.]+)")


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark budget gates")
    parser.add_argument("--min-bvh-speedup", type=float, default=2.0, help="Minimum BVH speedup multiplier")
    parser.add_argument(
        "--max-occlusion-second-run-s",
        type=float,
        default=60.0,
        help="Maximum allowed second-run latency (seconds) for benchmarks/bench_occlusion.py",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]

    print("[bench] bvh_occlusion")
    bvh_out = _run([sys.executable, str(root / "benchmarks" / "bench_bvh_occlusion.py")])
    match = SPEEDUP_RE.search(bvh_out)
    if match is None:
        print(bvh_out)
        raise SystemExit("Could not parse BVH speedup from benchmark output")
    speedup = float(match.group(1))
    if speedup < args.min_bvh_speedup:
        raise SystemExit(f"BVH speedup {speedup:.2f}x below threshold {args.min_bvh_speedup:.2f}x")
    print(f"[bench] bvh speedup ok: {speedup:.2f}x >= {args.min_bvh_speedup:.2f}x")

    print("[bench] occlusion")
    occ_out = _run([sys.executable, str(root / "benchmarks" / "bench_occlusion.py")])
    match = SECOND_RUN_RE.search(occ_out)
    if match is None:
        print(occ_out)
        raise SystemExit("Could not parse second_run_s from occlusion benchmark output")
    second_run_s = float(match.group(1))
    if second_run_s > args.max_occlusion_second_run_s:
        raise SystemExit(
            f"occlusion second run {second_run_s:.4f}s exceeds threshold {args.max_occlusion_second_run_s:.4f}s"
        )
    print(
        "[bench] occlusion second run ok: "
        f"{second_run_s:.4f}s <= {args.max_occlusion_second_run_s:.4f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
