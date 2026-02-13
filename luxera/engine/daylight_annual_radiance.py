from __future__ import annotations
"""Contract: docs/spec/daylight_contract.md, docs/spec/solver_contracts.md."""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from luxera.backends.radiance import detect_radiance_tools
from luxera.engine.daylight_df import DaylightResult, DaylightTargetResult, run_daylight_df
from luxera.project.schema import DaylightAnnualSpec, DaylightSpec, JobSpec, OpeningSpec, Project


def _resolve_weather_path(project: Project, annual: DaylightAnnualSpec) -> Path:
    if not annual.weather_file:
        raise RuntimeError("Daylight annual mode requires weather_file")
    p = Path(annual.weather_file).expanduser()
    if p.is_absolute():
        return p
    root = Path(project.root_dir or ".").expanduser().resolve()
    return (root / p).resolve()


def _read_epw_rows(path: Path) -> List[Tuple[int, int, float, float, float, float]]:
    rows: List[Tuple[int, int, float, float, float, float]] = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("LOCATION", "DESIGN", "TYPICAL", "GROUND", "HOLIDAYS", "COMMENTS", "DATA")):
            continue
        parts = [x.strip() for x in s.split(",")]
        if len(parts) < 16:
            continue
        try:
            month = int(parts[1])
            day = int(parts[2])
            hour_end = int(float(parts[3]))
            hour_mid = max(0.0, min(24.0, float(hour_end) - 0.5))
            ghi = max(0.0, float(parts[13])) if parts[13] else 0.0
            dni = max(0.0, float(parts[14])) if parts[14] else 0.0
            dhi = max(0.0, float(parts[15])) if parts[15] else 0.0
            rows.append((month, day, hour_mid, dni, dhi, ghi))
        except Exception:
            continue
    if not rows:
        raise RuntimeError(f"No weather timesteps parsed from EPW: {path}")
    return rows


def _read_epw_exterior_lux_proxy(path: Path) -> np.ndarray:
    vals: List[float] = []
    for _month, _day, _hour_mid, dni, dhi, ghi in _read_epw_rows(path):
        w_m2 = max(ghi, dni * 0.7 + dhi)
        vals.append(w_m2 * 120.0)
    return np.asarray(vals, dtype=float)


def _occupancy_mask(hours: int, schedule: str | list[float]) -> np.ndarray:
    if isinstance(schedule, list):
        arr = np.asarray([float(x) for x in schedule], dtype=float)
        if arr.size == 0:
            return np.ones((hours,), dtype=float)
        reps = int(np.ceil(hours / max(arr.size, 1)))
        out = np.tile(arr, reps)[:hours]
        return np.clip(out, 0.0, 1.0)
    sched = str(schedule or "office_8_to_18").lower()
    if sched == "always_on":
        return np.ones((hours,), dtype=float)
    mask = np.zeros((hours,), dtype=float)
    for i in range(hours):
        hod = i % 24
        if 8 <= hod < 18:
            mask[i] = 1.0
    return mask


def _rgb_to_lux(rgb: Tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 179.0 * (0.265 * r + 0.670 * g + 0.065 * b)


def _run_cmd(args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    proc = subprocess.run(args, input=input_bytes, capture_output=True, check=True)
    return proc.stdout


def _matrix_tooling_available() -> tuple[bool, dict[str, str]]:
    names = ("epw2wea", "gendaymtx", "dctimestep", "rfluxmtx", "oconv")
    paths = {n: (shutil.which(n) or "") for n in names}
    ok = all(bool(paths[n]) for n in names)
    return ok, paths


def _prepare_matrix_artifacts(epw_path: Path) -> tuple[Path, Path]:
    epw2wea = shutil.which("epw2wea")
    gendaymtx = shutil.which("gendaymtx")
    if not epw2wea or not gendaymtx:
        raise RuntimeError("Matrix preprocessing requires epw2wea and gendaymtx")
    td = Path(tempfile.mkdtemp(prefix="luxera_daylight_matrix_"))
    wea = td / "weather.wea"
    sky = td / "sky.mtx"
    subprocess.run([epw2wea, str(epw_path), str(wea)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    with sky.open("wb") as f:
        subprocess.run([gendaymtx, "-m", "1", str(wea)], stdout=f, stderr=subprocess.DEVNULL, check=True)
    return wea, sky


def _write_simple_scene(project: Project, path: Path, spec: DaylightSpec) -> None:
    lines: List[str] = []
    lines += [
        "void plastic wall_mat",
        "0",
        "0",
        "5 0.5 0.5 0.5 0 0",
        "",
        "void plastic floor_mat",
        "0",
        "0",
        "5 0.2 0.2 0.2 0 0",
        "",
        "void plastic ceil_mat",
        "0",
        "0",
        "5 0.7 0.7 0.7 0 0",
        "",
    ]

    def add_poly(mat: str, name: str, pts: List[Tuple[float, float, float]]) -> None:
        if len(pts) < 3:
            return
        coords = " ".join(f"{x:.6f} {y:.6f} {z:.6f}" for x, y, z in pts)
        lines.extend([f"{mat} polygon {name}", "0", "0", f"{len(pts) * 3} {coords}", ""])

    for i, room in enumerate(project.geometry.rooms):
        x0, y0, z0 = room.origin
        x1, y1, z1 = x0 + room.width, y0 + room.length, z0 + room.height
        add_poly("floor_mat", f"room_{i}_floor", [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)])
        add_poly("ceil_mat", f"room_{i}_ceil", [(x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1)])
        add_poly("wall_mat", f"room_{i}_w0", [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)])
        add_poly("wall_mat", f"room_{i}_w1", [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)])
        add_poly("wall_mat", f"room_{i}_w2", [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)])
        add_poly("wall_mat", f"room_{i}_w3", [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)])

    for i, op in enumerate(project.geometry.openings):
        if not op.is_daylight_aperture:
            continue
        vt_raw = op.vt if op.vt is not None else op.visible_transmittance
        vt = float(vt_raw if vt_raw is not None else spec.glass_visible_transmittance_default)
        vt = max(0.01, min(1.0, vt))
        mat = f"win_mat_{i}"
        lines += [f"void glass {mat}", "0", "0", f"3 {vt:.6f} {vt:.6f} {vt:.6f}", ""]
        add_poly(mat, f"window_{i}", [(float(x), float(y), float(z)) for x, y, z in op.vertices])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_sky_receiver(path: Path) -> None:
    # rfluxmtx control comments for Klems/Reinhart sky bins
    txt = "\n".join(
        [
            "#@rfluxmtx h=r1 u=Y",
            "void glow skyglow",
            "0",
            "0",
            "4 1 1 1 0",
            "skyglow source sky",
            "0",
            "0",
            "4 0 0 1 180",
            "",
        ]
    )
    path.write_text(txt + "\n", encoding="utf-8")


def _try_full_matrix_transfer(
    project: Project,
    targets: List[DaylightTargetResult],
    weather_path: Path,
    spec: DaylightSpec,
) -> tuple[dict[str, np.ndarray], Dict[str, object]]:
    epw2wea = shutil.which("epw2wea")
    gendaymtx = shutil.which("gendaymtx")
    oconv = shutil.which("oconv")
    rfluxmtx = shutil.which("rfluxmtx")
    dctimestep = shutil.which("dctimestep")
    if not all((epw2wea, gendaymtx, oconv, rfluxmtx, dctimestep)):
        raise RuntimeError("Missing required tools for full matrix transfer")

    all_points: List[Tuple[float, float, float]] = []
    slices: Dict[str, tuple[int, int]] = {}
    cursor = 0
    for t in targets:
        pts = np.asarray(t.points, dtype=float)
        n = int(pts.shape[0])
        all_points.extend((float(x), float(y), float(z)) for x, y, z in pts)
        slices[t.target_id] = (cursor, cursor + n)
        cursor += n
    if not all_points:
        return {}, {"status": "empty_points"}

    with tempfile.TemporaryDirectory(prefix="luxera_daylight_full_matrix_") as td:
        tdp = Path(td)
        wea = tdp / "weather.wea"
        sky_mtx = tdp / "sky.mtx"
        scene_rad = tdp / "scene.rad"
        scene_oct = tdp / "scene.oct"
        sensors_pts = tdp / "sensors.pts"
        sky_recv = tdp / "sky_receiver.rad"
        dc_mtx = tdp / "daylight_coeff.mtx"

        subprocess.run([epw2wea, str(weather_path), str(wea)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        with sky_mtx.open("wb") as f:
            subprocess.run([gendaymtx, "-m", "1", str(wea)], stdout=f, stderr=subprocess.DEVNULL, check=True)

        _write_simple_scene(project, scene_rad, spec)
        _write_sky_receiver(sky_recv)
        with scene_oct.open("wb") as f:
            subprocess.run([oconv, str(scene_rad), str(sky_recv)], stdout=f, stderr=subprocess.DEVNULL, check=True)

        sensors_pts.write_text("\n".join(f"{x:.6f} {y:.6f} {z:.6f} 0 0 1" for x, y, z in all_points) + "\n", encoding="utf-8")

        # Daylight coefficient matrix: rows=points, cols=sky patches
        with dc_mtx.open("wb") as f_out:
            subprocess.run(
                [
                    rfluxmtx,
                    "-I+",
                    "-ab",
                    "1",
                    "-ad",
                    "256",
                    "-lw",
                    "1e-4",
                    str(sky_recv),
                    str(scene_oct),
                ],
                input=sensors_pts.read_bytes(),
                stdout=f_out,
                stderr=subprocess.DEVNULL,
                check=True,
            )

        # Multiply daylight coefficients with sky matrix -> hourly illuminance per point
        raw = subprocess.run([dctimestep, str(dc_mtx), str(sky_mtx)], capture_output=True, check=True).stdout.decode("utf-8", errors="replace")
        rows: List[List[float]] = []
        for ln in raw.splitlines():
            s = ln.strip()
            if not s:
                continue
            toks = s.split()
            if len(toks) >= 3:
                try:
                    rows.append([_rgb_to_lux((float(toks[0]), float(toks[1]), float(toks[2])) )])
                except Exception:
                    continue
        if not rows:
            raise RuntimeError("dctimestep returned no rows")

        # dctimestep output is point-major scalar rows for this invocation; reshape by point count.
        vals = np.asarray([r[0] for r in rows], dtype=float)
        n_points = len(all_points)
        if vals.size % n_points != 0:
            raise RuntimeError(f"Unexpected dctimestep output size: {vals.size} for {n_points} points")
        hours = vals.size // n_points
        point_hour = vals.reshape((n_points, hours)).T  # hours x points

        per_target: dict[str, np.ndarray] = {}
        for tid, (a, b) in slices.items():
            per_target[tid] = point_hour[:, a:b]

        return per_target, {
            "status": "ok",
            "mode": "full_matrix",
            "hours": int(hours),
            "n_points": int(n_points),
            "artifacts": {
                "weather_wea": str(wea),
                "sky_mtx": str(sky_mtx),
                "scene_rad": str(scene_rad),
                "scene_oct": str(scene_oct),
                "sensors_pts": str(sensors_pts),
                "daylight_coeff_mtx": str(dc_mtx),
            },
        }


def _radiance_hourly_exterior_lux(epw_rows: List[Tuple[int, int, float, float, float, float]]) -> np.ndarray:
    gendaylit = shutil.which("gendaylit")
    oconv = shutil.which("oconv")
    rtrace = shutil.which("rtrace")
    if not gendaylit or not oconv or not rtrace:
        raise RuntimeError("Radiance hourly exterior run requires gendaylit, oconv, and rtrace")

    vals: List[float] = []
    with tempfile.TemporaryDirectory(prefix="luxera_daylight_annual_") as td:
        tdp = Path(td)
        sky_rad = tdp / "sky.rad"
        sky_oct = tdp / "sky.oct"
        for month, day, hour_mid, dni, dhi, ghi in epw_rows:
            if (dni + dhi + ghi) <= 1e-9:
                vals.append(0.0)
                continue
            cmd = [gendaylit, str(month), str(day), f"{hour_mid:.3f}", "-W", f"{dni:.6f}", f"{dhi:.6f}"]
            sky_text = _run_cmd(cmd).decode("utf-8", errors="replace")
            sky_rad.write_text(sky_text, encoding="utf-8")
            with sky_oct.open("wb") as f:
                subprocess.run([oconv, str(sky_rad)], stdout=f, stderr=subprocess.DEVNULL, check=True)
            pt = b"0 0 0 0 0 1\n"
            out = _run_cmd([rtrace, "-h", "-I+", str(sky_oct)], input_bytes=pt).decode("utf-8", errors="replace").strip()
            toks = out.split()
            if len(toks) >= 3:
                try:
                    rgb = (float(toks[0]), float(toks[1]), float(toks[2]))
                    vals.append(float(_rgb_to_lux(rgb)))
                    continue
                except Exception:
                    pass
            vals.append(0.0)
    return np.asarray(vals, dtype=float)


def run_daylight_annual_radiance(project: Project, job: JobSpec, scene: object | None = None) -> DaylightResult:  # noqa: ARG001
    tools = detect_radiance_tools()
    if not tools.available:
        missing = ", ".join(tools.missing)
        raise RuntimeError(f"Radiance tooling not available for annual daylight mode (missing: {missing})")

    spec = job.daylight or DaylightSpec(mode="annual")
    annual = spec.annual or DaylightAnnualSpec()
    weather_path = _resolve_weather_path(project, annual)
    epw_rows = _read_epw_rows(weather_path)

    pref = str(annual.annual_method_preference or "auto")
    matrix_ok, matrix_paths = _matrix_tooling_available()
    matrix_artifacts: Dict[str, object] = {"requested": pref, "available": matrix_ok, "paths": matrix_paths}

    # Baseline deterministic point coupling from DF geometry factors.
    target_ids = list(annual.grid_targets) if annual.grid_targets else list(job.targets)
    base_job = JobSpec(
        id=f"{job.id}:annual_base",
        type="daylight",
        backend="radiance",
        daylight=DaylightSpec(mode="df", sky=spec.sky, glass_visible_transmittance_default=spec.glass_visible_transmittance_default),
        targets=target_ids,
    )
    base = run_daylight_df(project, base_job, scene=scene)

    target_hourly: Dict[str, np.ndarray] = {}
    annual_method = "epw_proxy_df_transfer"

    if pref in {"matrix", "auto"} and matrix_ok:
        try:
            target_hourly, matrix_info = _try_full_matrix_transfer(project, base.targets, weather_path, spec)
            matrix_artifacts.update(matrix_info)
            annual_method = "radiance_full_matrix_dctimestep"
        except Exception as exc:
            matrix_artifacts["full_matrix_error"] = str(exc)
            if pref == "matrix":
                raise RuntimeError(f"Matrix-preferred annual daylight failed: {exc}")

    if not target_hourly:
        # Fallback hourly exterior illuminance transfer path.
        toolchain_ok = all(shutil.which(x) for x in ("gendaylit", "oconv", "rtrace"))
        if toolchain_ok:
            ext_lux = _radiance_hourly_exterior_lux(epw_rows)
            annual_method = "radiance_epw_gendaylit_df_transfer"
        else:
            ext_lux = _read_epw_exterior_lux_proxy(weather_path)
            annual_method = "epw_proxy_df_transfer"
            if pref == "hourly_rtrace":
                raise RuntimeError("Hourly-rtrace annual daylight requested but gendaylit/oconv/rtrace tooling is unavailable")

        for tr in base.targets:
            df_ratio = np.clip(tr.values.reshape(-1) / 100.0, 0.0, 1.0)
            target_hourly[tr.target_id] = ext_lux[:, None] * df_ratio[None, :]

    hours_any = int(next(iter(target_hourly.values())).shape[0]) if target_hourly else 0
    occ = _occupancy_mask(hours_any, annual.occupancy_schedule)

    targets: List[DaylightTargetResult] = []
    annual_metrics: List[Dict[str, object]] = []
    sda_area_pass: List[float] = []
    ase_area_fail: List[float] = []
    udi_area: List[float] = []

    base_by_id = {t.target_id: t for t in base.targets}
    for tid, ei in target_hourly.items():
        tr = base_by_id.get(tid)
        if tr is None:
            continue
        occ_ei = ei * occ[:, None]
        occ_hours = np.maximum(np.sum(occ > 0.0), 1)
        sda_point = 100.0 * np.mean(occ_ei >= float(annual.sda_target_lux), axis=0)
        ase_hours = np.sum(ei >= float(annual.ase_threshold_lux), axis=0)
        ase_point = 100.0 * (ase_hours > float(annual.ase_hours_limit)).astype(float)
        udi_point = 100.0 * np.mean((occ_ei >= float(annual.udi_low)) & (occ_ei <= float(annual.udi_high)), axis=0)

        targets.append(
            DaylightTargetResult(
                target_id=tr.target_id,
                target_type=tr.target_type,
                points=tr.points,
                values=sda_point,
                nx=tr.nx,
                ny=tr.ny,
            )
        )

        sda_area = float(np.mean(sda_point >= float(annual.sda_target_percent))) * 100.0 if sda_point.size else 0.0
        ase_area = float(np.mean(ase_hours > float(annual.ase_hours_limit))) * 100.0 if ase_hours.size else 0.0
        udi_mean = float(np.mean(udi_point)) if udi_point.size else 0.0
        sda_area_pass.append(sda_area)
        ase_area_fail.append(ase_area)
        udi_area.append(udi_mean)

        annual_metrics.append(
            {
                "target_id": tr.target_id,
                "target_type": tr.target_type,
                "hours": int(ei.shape[0]),
                "occupied_hours": int(occ_hours),
                "sda_point_percent": sda_point.tolist(),
                "ase_point_percent": ase_point.tolist(),
                "udi_point_percent": udi_point.tolist(),
                "sda_area_percent": sda_area,
                "ase_area_percent": ase_area,
                "udi_mean_percent": udi_mean,
                "sda_target_lux": float(annual.sda_target_lux),
                "sda_target_percent": float(annual.sda_target_percent),
                "ase_threshold_lux": float(annual.ase_threshold_lux),
                "ase_hours_limit": float(annual.ase_hours_limit),
                "udi_low": float(annual.udi_low),
                "udi_high": float(annual.udi_high),
                "illuminance_hourly_mean_lux": np.mean(ei, axis=1).tolist(),
            }
        )

    summary: Dict[str, object] = {
        "mode": "annual",
        "metric": "annual_daylight",
        "sky": spec.sky,
        "radiance_quality": spec.radiance_quality,
        "random_seed": int(spec.random_seed),
        "weather_file": str(weather_path),
        "occupancy_schedule": annual.occupancy_schedule,
        "annual_hours": hours_any,
        "sda_area_percent_mean": float(np.mean(sda_area_pass)) if sda_area_pass else 0.0,
        "ase_area_percent_mean": float(np.mean(ase_area_fail)) if ase_area_fail else 0.0,
        "udi_percent_mean": float(np.mean(udi_area)) if udi_area else 0.0,
        "thresholds": {
            "sda_target_lux": float(annual.sda_target_lux),
            "sda_target_percent": float(annual.sda_target_percent),
            "ase_threshold_lux": float(annual.ase_threshold_lux),
            "ase_hours_limit": float(annual.ase_hours_limit),
            "udi_low": float(annual.udi_low),
            "udi_high": float(annual.udi_high),
        },
        "radiance_tools": tools.paths,
        "annual_method": annual_method,
        "matrix_artifacts": matrix_artifacts,
        "annual_metrics": annual_metrics,
    }
    return DaylightResult(summary=summary, targets=targets)
