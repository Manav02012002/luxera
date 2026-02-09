from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from luxera.parser.pipeline import parse_and_analyse_ies
from luxera.plotting.plots import save_default_plots
from luxera.export.pdf_report import build_pdf_report
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.schema import (
    Project,
    PhotometryAsset,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    TransformSpec,
    RotationSpec,
    RoomSpec,
)
from luxera.project.presets import en12464_direct_job, en13032_radiosity_job
from luxera.core.hashing import sha256_file


_DEMO_IES_TEXT = """IESNA:LM-63-2002
[MANUFAC] Luxera Demo
[LUMCAT] DEMO-001
TILT=NONE
1 16000 2 3 2 1 2 0.45 0.45 0.10
0 45 90
0 180
0 1 2
3 4 5
"""


def _cmd_demo(args: argparse.Namespace) -> int:
    outpath = Path(args.out).expanduser().resolve()
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(_DEMO_IES_TEXT, encoding="utf-8")
    print(f"Saved demo IES to: {outpath}")
    return 0


def _cmd_view(args: argparse.Namespace) -> int:
    ies_path = Path(args.file).expanduser().resolve()
    outdir = Path(args.out).expanduser().resolve()
    stem = args.stem
    make_pdf = bool(args.pdf)

    if not ies_path.exists():
        print(f"[ERROR] File not found: {ies_path}")
        print("        Provide a valid path to a .ies file.")
        return 2
    if not ies_path.is_file():
        print(f"[ERROR] Not a file: {ies_path}")
        return 2

    text = ies_path.read_text(encoding="utf-8", errors="replace")
    res = parse_and_analyse_ies(text)

    if res.doc.photometry is None or res.doc.angles is None or res.doc.candela is None:
        print("[ERROR] Failed to parse photometry/angles/candela; cannot plot/report.")
        return 3

    paths = save_default_plots(res.doc, outdir, stem=stem)

    pdf_path = None
    if make_pdf:
        pdf_path = outdir / f"{stem}_report.pdf"
        build_pdf_report(res, paths, pdf_path, source_file=ies_path)

    print("Luxera View")
    print(f"  File: {ies_path}")
    print(f"  Saved: {paths.intensity_png}")
    print(f"  Saved: {paths.polar_png}")
    if pdf_path is not None:
        print(f"  Saved: {pdf_path}")

    if res.derived is not None:
        print(
            f"  Peak candela: {res.derived.peak_candela:g} "
            f"at (H,V)=({res.derived.peak_location[0]:g}°, {res.derived.peak_location[1]:g}°)"
        )

    if res.report is not None:
        s = res.report.summary
        print(f"  Findings: {s['errors']} error(s), {s['warnings']} warning(s), {s['info']} info")

    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    # Import here so CLI still works even if PySide6 isn't installed
    from luxera.gui.app import run
    return int(run())


def _cmd_init_project(args: argparse.Namespace) -> int:
    path = Path(args.project).expanduser().resolve()
    name = args.name or path.stem
    project = Project(name=name, root_dir=str(path.parent))
    save_project_schema(project, path)
    print(f"Initialized project: {path}")
    return 0


def _cmd_add_photometry(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)

    src = Path(args.file).expanduser().resolve()
    if not src.exists() or not src.is_file():
        print(f"[ERROR] Photometry file not found: {src}")
        return 2

    fmt = args.format.upper() if args.format else src.suffix.replace(".", "").upper()
    if fmt not in ("IES", "LDT"):
        print(f"[ERROR] Unsupported photometry format: {fmt}")
        return 2

    asset_id = args.id or str(uuid.uuid4())
    asset = PhotometryAsset(
        id=asset_id,
        format=fmt,  # type: ignore[arg-type]
        path=str(src),
        content_hash=sha256_file(str(src)),
        metadata={"filename": src.name},
    )
    project.photometry_assets.append(asset)
    save_project_schema(project, project_path)
    print(f"Added photometry asset: {asset_id}")
    return 0


def _cmd_add_luminaire(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)

    if args.asset not in [a.id for a in project.photometry_assets]:
        print(f"[ERROR] Photometry asset not found: {args.asset}")
        return 2

    lum_id = args.id or str(uuid.uuid4())
    rotation = RotationSpec(type="euler_zyx", euler_deg=(args.yaw, args.pitch, args.roll))
    transform = TransformSpec(position=(args.x, args.y, args.z), rotation=rotation)
    lum = LuminaireInstance(
        id=lum_id,
        name=args.name or f"Luminaire {lum_id[:8]}",
        photometry_asset_id=args.asset,
        transform=transform,
        maintenance_factor=args.maintenance,
        flux_multiplier=args.multiplier,
        tilt_deg=args.tilt,
    )
    project.luminaires.append(lum)
    save_project_schema(project, project_path)
    print(f"Added luminaire: {lum_id}")
    return 0


def _cmd_add_grid(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)

    grid_id = args.id or str(uuid.uuid4())
    grid = CalcGrid(
        id=grid_id,
        name=args.name or f"Grid {grid_id[:8]}",
        origin=(args.origin_x, args.origin_y, args.origin_z),
        width=args.width,
        height=args.height,
        elevation=args.elevation,
        nx=args.nx,
        ny=args.ny,
    )
    project.grids.append(grid)
    save_project_schema(project, project_path)
    print(f"Added grid: {grid_id}")
    return 0


def _cmd_add_room(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)

    room_id = args.id or str(uuid.uuid4())
    room = RoomSpec(
        id=room_id,
        name=args.name or f"Room {room_id[:8]}",
        width=args.width,
        length=args.length,
        height=args.height,
        origin=(args.origin_x, args.origin_y, args.origin_z),
        floor_reflectance=args.floor_reflectance,
        wall_reflectance=args.wall_reflectance,
        ceiling_reflectance=args.ceiling_reflectance,
        activity_type=args.activity_type,
    )
    project.geometry.rooms.append(room)
    save_project_schema(project, project_path)
    print(f"Added room: {room_id}")
    return 0


def _cmd_add_job(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)

    job_id = args.id or str(uuid.uuid4())
    if args.preset == "en12464_direct":
        job = en12464_direct_job(job_id)
    elif args.preset == "en13032_radiosity":
        job = en13032_radiosity_job(job_id)
    else:
        settings = {}
        if args.type == "radiosity":
            use_visibility = args.use_visibility and not args.no_visibility
            eye_heights = [float(x) for x in args.ugr_eye_heights.split(",") if x.strip()] if args.ugr_eye_heights else [1.2, 1.7]
            settings = {
                "max_iterations": args.max_iterations,
                "convergence_threshold": args.convergence_threshold,
                "patch_max_area": args.patch_max_area,
                "method": args.method,
                "use_visibility": use_visibility,
                "ambient_light": args.ambient_light,
                "monte_carlo_samples": args.monte_carlo_samples,
                "ugr_grid_spacing": args.ugr_grid_spacing,
                "ugr_eye_heights": eye_heights,
            }

        job = JobSpec(
            id=job_id,
            type=args.type,  # type: ignore[arg-type]
            backend="cpu",
            settings=settings,
            seed=args.seed,
        )
    project.jobs.append(job)
    save_project_schema(project, project_path)
    print(f"Added job: {job_id}")
    return 0


def _cmd_run_job(args: argparse.Namespace) -> int:
    from luxera.runner import run_job

    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)

    ref = run_job(project, args.job_id)
    save_project_schema(project, project_path)
    print(f"Job completed: {ref.job_id}")
    print(f"  Result dir: {ref.result_dir}")
    return 0


def _cmd_export_debug(args: argparse.Namespace) -> int:
    from luxera.export.debug_bundle import export_debug_bundle

    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    job_id = args.job_id
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        print(f"[ERROR] Job result not found: {job_id}")
        return 2
    out = export_debug_bundle(project, ref, Path(args.out))
    print(f"Debug bundle written: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="luxera")
    sub = p.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="Write a small demo .ies file to disk.")
    demo.add_argument("--out", default="data/ies_samples/demo.ies", help="Output .ies path")
    demo.set_defaults(func=_cmd_demo)

    v = sub.add_parser("view", help="Parse an IES file and save default plots (PNG), optionally PDF.")
    v.add_argument("file", help="Path to .ies file")
    v.add_argument("--out", default="out", help="Output directory (default: out)")
    v.add_argument("--stem", default="luxera_view", help="Filename stem for outputs")
    v.add_argument("--pdf", action="store_true", help="Also generate a PDF report")
    v.set_defaults(func=_cmd_view)

    g = sub.add_parser("gui", help="Launch Luxera View interactive GUI.")
    g.set_defaults(func=_cmd_gui)

    init = sub.add_parser("init", help="Initialize a new Luxera project file (schema v1).")
    init.add_argument("project", help="Path to project JSON")
    init.add_argument("--name", default=None, help="Project name (default: filename stem)")
    init.set_defaults(func=_cmd_init_project)

    ap = sub.add_parser("add-photometry", help="Add an IES/LDT asset to a project.")
    ap.add_argument("project", help="Path to project JSON")
    ap.add_argument("file", help="Path to IES/LDT file")
    ap.add_argument("--id", default=None, help="Optional asset id")
    ap.add_argument("--format", default=None, help="Override format (IES or LDT)")
    ap.set_defaults(func=_cmd_add_photometry)

    al = sub.add_parser("add-luminaire", help="Add a luminaire instance to a project.")
    al.add_argument("project", help="Path to project JSON")
    al.add_argument("--asset", required=True, help="Photometry asset id")
    al.add_argument("--id", default=None, help="Optional luminaire id")
    al.add_argument("--name", default=None, help="Luminaire name")
    al.add_argument("--x", type=float, required=True)
    al.add_argument("--y", type=float, required=True)
    al.add_argument("--z", type=float, required=True)
    al.add_argument("--yaw", type=float, default=0.0)
    al.add_argument("--pitch", type=float, default=0.0)
    al.add_argument("--roll", type=float, default=0.0)
    al.add_argument("--maintenance", type=float, default=1.0)
    al.add_argument("--multiplier", type=float, default=1.0)
    al.add_argument("--tilt", type=float, default=0.0, help="Luminaire tilt angle (degrees)")
    al.set_defaults(func=_cmd_add_luminaire)

    ag = sub.add_parser("add-grid", help="Add a calculation grid to a project.")
    ag.add_argument("project", help="Path to project JSON")
    ag.add_argument("--id", default=None, help="Optional grid id")
    ag.add_argument("--name", default=None, help="Grid name")
    ag.add_argument("--origin-x", type=float, default=0.0)
    ag.add_argument("--origin-y", type=float, default=0.0)
    ag.add_argument("--origin-z", type=float, default=0.0)
    ag.add_argument("--width", type=float, required=True)
    ag.add_argument("--height", type=float, required=True)
    ag.add_argument("--elevation", type=float, required=True)
    ag.add_argument("--nx", type=int, required=True)
    ag.add_argument("--ny", type=int, required=True)
    ag.set_defaults(func=_cmd_add_grid)

    ar = sub.add_parser("add-room", help="Add a simple rectangular room to a project.")
    ar.add_argument("project", help="Path to project JSON")
    ar.add_argument("--id", default=None, help="Optional room id")
    ar.add_argument("--name", default=None, help="Room name")
    ar.add_argument("--width", type=float, required=True)
    ar.add_argument("--length", type=float, required=True)
    ar.add_argument("--height", type=float, required=True)
    ar.add_argument("--origin-x", type=float, default=0.0)
    ar.add_argument("--origin-y", type=float, default=0.0)
    ar.add_argument("--origin-z", type=float, default=0.0)
    ar.add_argument("--floor-reflectance", type=float, default=0.2)
    ar.add_argument("--wall-reflectance", type=float, default=0.5)
    ar.add_argument("--ceiling-reflectance", type=float, default=0.7)
    ar.add_argument("--activity-type", default=None, help="EN 12464 activity type enum name")
    ar.set_defaults(func=_cmd_add_room)

    aj = sub.add_parser("add-job", help="Add a calculation job to a project.")
    aj.add_argument("project", help="Path to project JSON")
    aj.add_argument("--id", default=None, help="Optional job id")
    aj.add_argument("--type", choices=["direct", "radiosity"], default="direct")
    aj.add_argument("--seed", type=int, default=0)
    aj.add_argument("--preset", choices=["en12464_direct", "en13032_radiosity"], default=None)
    aj.add_argument("--max-iterations", type=int, default=100)
    aj.add_argument("--convergence-threshold", type=float, default=0.001)
    aj.add_argument("--patch-max-area", type=float, default=0.5)
    aj.add_argument("--method", choices=["GATHERING", "SHOOTING", "MATRIX"], default="GATHERING")
    aj.add_argument("--use-visibility", action="store_true", default=True)
    aj.add_argument("--no-visibility", action="store_true", default=False, help="Disable visibility in form factors")
    aj.add_argument("--ambient-light", type=float, default=0.0)
    aj.add_argument("--monte-carlo-samples", type=int, default=16)
    aj.add_argument("--ugr-grid-spacing", type=float, default=2.0)
    aj.add_argument("--ugr-eye-heights", type=str, default="1.2,1.7", help="Comma-separated eye heights in meters")
    aj.set_defaults(func=_cmd_add_job)

    rj = sub.add_parser("run", help="Run a project job and store results.")
    rj.add_argument("project", help="Path to project JSON")
    rj.add_argument("job_id", help="Job id to run")
    rj.set_defaults(func=_cmd_run_job)

    db = sub.add_parser("export-debug", help="Export a debug bundle zip for a job result.")
    db.add_argument("project", help="Path to project JSON")
    db.add_argument("job_id", help="Job id to export")
    db.add_argument("--out", required=True, help="Output .zip path")
    db.set_defaults(func=_cmd_export_debug)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
