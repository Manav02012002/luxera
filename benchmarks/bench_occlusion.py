from __future__ import annotations

import time
from pathlib import Path

from luxera.engine.direct_illuminance import (
    build_direct_occlusion_context,
    load_luminaires,
    run_direct_grid,
)
from luxera.project.schema import (
    CalcGrid,
    LuminaireInstance,
    PhotometryAsset,
    Project,
    RotationSpec,
    SurfaceSpec,
    TransformSpec,
)


def _ies_fixture(path: Path) -> Path:
    path.write_text(
        """IESNA:LM-63-2019
TILT=NONE
1 1200 1 3 1 1 2 0.5 0.5 0.2
0 45 90
0
1200 800 300
""",
        encoding="utf-8",
    )
    return path


def _build_scene(tmp_dir: Path, blockers_nx: int = 50, blockers_ny: int = 50) -> Project:
    tmp_dir = tmp_dir.resolve()
    ies = _ies_fixture((tmp_dir / "bench.ies").resolve())
    p = Project(name="bench_occlusion", root_dir=str(tmp_dir))
    p.photometry_assets.append(PhotometryAsset(id="a1", format="IES", path=str(ies)))
    rot = RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0))
    p.luminaires.append(
        LuminaireInstance(
            id="l1",
            name="Lum",
            photometry_asset_id="a1",
            transform=TransformSpec(position=(5.0, 5.0, 6.0), rotation=rot),
        )
    )
    # 2 triangles per quad equivalent: use one 4-vertex polygon per cell.
    dx = 10.0 / blockers_nx
    dy = 10.0 / blockers_ny
    z = 3.0
    sid = 0
    for j in range(blockers_ny):
        for i in range(blockers_nx):
            x0 = i * dx
            y0 = j * dy
            x1 = x0 + dx * 0.9
            y1 = y0 + dy * 0.9
            sid += 1
            p.geometry.surfaces.append(
                SurfaceSpec(
                    id=f"b_{sid}",
                    name=f"b_{sid}",
                    kind="custom",
                    vertices=[(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)],
                )
            )
    return p


def main() -> int:
    tmp_dir = (Path(".") / "dist" / "bench_occlusion").resolve()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    project = _build_scene(tmp_dir, blockers_nx=50, blockers_ny=50)  # ~5000 triangles after triangulation
    luminaires, _ = load_luminaires(project, lambda a: "hash")
    grid = CalcGrid(id="g1", name="grid", origin=(0.0, 0.0, 0.0), width=10.0, height=10.0, elevation=0.8, nx=80, ny=80)

    t0 = time.perf_counter()
    occ = build_direct_occlusion_context(project, include_room_shell=False, occlusion_epsilon=1e-6)
    t1 = time.perf_counter()
    res = run_direct_grid(grid, luminaires, occlusion=occ, use_occlusion=True, occlusion_epsilon=1e-6)
    t2 = time.perf_counter()
    res2 = run_direct_grid(grid, luminaires, occlusion=occ, use_occlusion=True, occlusion_epsilon=1e-6)
    t3 = time.perf_counter()

    print("bench_occlusion")
    print(f"  triangles: {len(occ.triangles)}")
    print(f"  points: {grid.nx * grid.ny}")
    print(f"  bvh_build_s: {t1 - t0:.4f}")
    print(f"  first_run_s: {t2 - t1:.4f}")
    print(f"  second_run_s: {t3 - t2:.4f}")
    print(f"  mean_lux_run1: {float(res.values.mean()):.6f}")
    print(f"  mean_lux_run2: {float(res2.values.mean()):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
