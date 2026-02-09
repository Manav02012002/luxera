from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import List

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
    RoadwayGridSpec,
    ComplianceProfile,
)
from luxera.project.presets import en12464_direct_job, en13032_radiosity_job, default_compliance_profiles
from luxera.core.hashing import sha256_file
from luxera.photometry.verify import verify_photometry_file
from luxera.io.geometry_import import import_geometry_file
from luxera.geometry.scene_prep import clean_scene_surfaces, detect_room_volumes_from_surfaces


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
        room_id=args.room_id,
        zone_id=args.zone_id,
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


def _cmd_add_roadway_grid(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    rg_id = args.id or str(uuid.uuid4())
    rg = RoadwayGridSpec(
        id=rg_id,
        name=args.name or f"Roadway Grid {rg_id[:8]}",
        lane_width=args.lane_width,
        road_length=args.road_length,
        nx=args.nx,
        ny=args.ny,
        origin=(args.origin_x, args.origin_y, args.origin_z),
        num_lanes=args.num_lanes,
        pole_spacing_m=args.pole_spacing_m,
        mounting_height_m=args.mounting_height_m,
        setback_m=args.setback_m,
        observer_height_m=args.observer_height_m,
    )
    project.roadway_grids.append(rg)
    save_project_schema(project, project_path)
    print(f"Added roadway grid: {rg_id}")
    return 0


def _cmd_add_compliance_profile(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    profile_id = args.id or str(uuid.uuid4())
    thresholds = json.loads(args.thresholds)
    if not isinstance(thresholds, dict):
        print("[ERROR] --thresholds must be a JSON object")
        return 2
    profile = ComplianceProfile(
        id=profile_id,
        name=args.name,
        domain=args.domain,
        standard_ref=args.standard_ref,
        thresholds={str(k): float(v) for k, v in thresholds.items()},
        notes=args.notes or "",
    )
    project.compliance_profiles.append(profile)
    save_project_schema(project, project_path)
    print(f"Added compliance profile: {profile_id}")
    return 0


def _cmd_add_profile_presets(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    existing = {cp.id for cp in project.compliance_profiles}
    added = 0
    for cp in default_compliance_profiles():
        if cp.id in existing:
            continue
        project.compliance_profiles.append(cp)
        existing.add(cp.id)
        added += 1
    save_project_schema(project, project_path)
    print(f"Added compliance profile presets: {added}")
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
        elif args.type in {"direct", "emergency"}:
            settings = {
                "use_occlusion": bool(args.use_occlusion and not args.no_occlusion),
                "occlusion_include_room_shell": bool(args.occlusion_include_room_shell),
                "occlusion_epsilon": args.occlusion_epsilon,
            }
            if args.type == "emergency":
                settings.update(
                    {
                        "mode": args.emergency_mode,
                        "target_min_lux": args.target_min_lux,
                        "target_uniformity": args.target_uniformity,
                        "compliance_profile_id": args.compliance_profile_id,
                        "battery_duration_min": args.battery_duration_min,
                        "battery_end_factor": args.battery_end_factor,
                        "battery_curve": args.battery_curve,
                        "battery_steps": args.battery_steps,
                    }
                )
        elif args.type == "roadway":
            settings = {
                "road_class": args.road_class,
                "compliance_profile_id": args.compliance_profile_id,
                "road_surface_reflectance": args.road_surface_reflectance,
                "observer_height_m": args.observer_height_m,
                "observer_back_offset_m": args.observer_back_offset_m,
                "observer_lateral_positions_m": [float(x) for x in args.observer_lateral_positions.split(",") if x.strip()]
                if args.observer_lateral_positions
                else None,
            }
        elif args.type == "daylight":
            exterior_hourly_lux: List[float] | None = None
            if args.weather_hourly_lux_file:
                raw = Path(args.weather_hourly_lux_file).expanduser().read_text(encoding="utf-8", errors="replace")
                toks = raw.replace("\n", ",").split(",")
                exterior_hourly_lux = [float(t.strip()) for t in toks if t.strip()]
            settings = {
                "mode": args.daylight_mode,
                "exterior_horizontal_illuminance_lux": args.exterior_horizontal_illuminance_lux,
                "daylight_factor_percent": args.daylight_factor_percent,
                "target_lux": args.daylight_target_lux,
                "annual_hours": args.annual_hours,
                "exterior_hourly_lux": exterior_hourly_lux,
                "daylight_depth_attenuation": args.daylight_depth_attenuation,
                "sda_threshold_ratio": args.sda_threshold_ratio,
                "udi_low_lux": args.udi_low_lux,
                "udi_high_lux": args.udi_high_lux,
            }

        job = JobSpec(
            id=job_id,
            type=args.type,  # type: ignore[arg-type]
            backend=args.backend,  # type: ignore[arg-type]
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
    from luxera.agent.audit import append_audit_event

    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    job_id = args.job_id
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        print(f"[ERROR] Job result not found: {job_id}")
        return 2
    out = export_debug_bundle(project, ref, Path(args.out))
    append_audit_event(
        project,
        action="export.debug_bundle",
        plan="Create full audit bundle for reproducibility.",
        artifacts=[str(out)],
        job_hashes=[ref.job_hash],
        metadata={"job_id": job_id},
    )
    save_project_schema(project, project_path)
    print(f"Debug bundle written: {out}")
    return 0


def _cmd_export_client(args: argparse.Namespace) -> int:
    from luxera.export.client_bundle import export_client_bundle
    from luxera.agent.audit import append_audit_event

    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    job_id = args.job_id
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        print(f"[ERROR] Job result not found: {job_id}")
        return 2
    out = export_client_bundle(project, ref, Path(args.out))
    append_audit_event(
        project,
        action="export.client_bundle",
        plan="Create client-facing report and key result artifact bundle.",
        artifacts=[str(out)],
        job_hashes=[ref.job_hash],
        metadata={"job_id": job_id},
    )
    save_project_schema(project, project_path)
    print(f"Client bundle written: {out}")
    return 0


def _cmd_export_backend_compare(args: argparse.Namespace) -> int:
    from luxera.export.backend_comparison import render_backend_comparison_html
    from luxera.agent.audit import append_audit_event

    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    job_id = args.job_id
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        print(f"[ERROR] Job result not found: {job_id}")
        return 2
    out = render_backend_comparison_html(Path(ref.result_dir), Path(args.out))
    append_audit_event(
        project,
        action="export.backend_comparison",
        plan="Render backend comparison report from result artifacts.",
        artifacts=[str(out)],
        job_hashes=[ref.job_hash],
        metadata={"job_id": job_id},
    )
    save_project_schema(project, project_path)
    print(f"Backend comparison report written: {out}")
    return 0


def _cmd_export_roadway_report(args: argparse.Namespace) -> int:
    from luxera.export.roadway_report import render_roadway_report_html
    from luxera.agent.audit import append_audit_event

    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    job_id = args.job_id
    ref = next((r for r in project.results if r.job_id == job_id), None)
    if ref is None:
        print(f"[ERROR] Job result not found: {job_id}")
        return 2
    out = render_roadway_report_html(Path(ref.result_dir), Path(args.out))
    append_audit_event(
        project,
        action="export.roadway_report",
        plan="Render roadway report from result artifacts.",
        artifacts=[str(out)],
        job_hashes=[ref.job_hash],
        metadata={"job_id": job_id},
    )
    save_project_schema(project, project_path)
    print(f"Roadway report written: {out}")
    return 0


def _cmd_compare_results(args: argparse.Namespace) -> int:
    from luxera.results.compare import compare_job_results

    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    try:
        cmp = compare_job_results(project, args.job_a, args.job_b)
    except Exception as e:
        print(f"[ERROR] Compare failed: {e}")
        return 2
    if args.out:
        out = Path(args.out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(cmp, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Comparison written: {out}")
    else:
        print(json.dumps(cmp, indent=2, sort_keys=True))
    return 0


def _cmd_photometry_verify(args: argparse.Namespace) -> int:
    try:
        result = verify_photometry_file(args.file, fmt=args.format)
    except Exception as e:
        print(f"[ERROR] Photometry verification failed: {e}")
        return 2

    data = result.to_dict()
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    print("Photometry Verify")
    print(f"  File: {data['file']}")
    print(f"  SHA256: {data['file_hash_sha256']}")
    print(f"  Format/System: {data['format']} / {data['photometric_system']}")
    print(f"  Symmetry: {data['symmetry']}")
    print(
        "  Angles: "
        f"C[{data['angle_ranges_deg']['c_min']:.1f}, {data['angle_ranges_deg']['c_max']:.1f}] "
        f"Gamma[{data['angle_ranges_deg']['gamma_min']:.1f}, {data['angle_ranges_deg']['gamma_max']:.1f}]"
    )
    print(
        "  Candela: "
        f"min={data['candela_stats']['min_cd']:.3g}, "
        f"max={data['candela_stats']['max_cd']:.3g}, "
        f"mean={data['candela_stats']['mean_cd']:.3g}"
    )
    print(f"  Coordinate convention: {data['coordinate_convention']}")
    if data["warnings"]:
        print("  Warnings:")
        for w in data["warnings"]:
            print(f"    - {w}")
    return 0


def _cmd_geometry_import(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    try:
        res = import_geometry_file(args.file, fmt=args.format, dxf_scale=args.dxf_scale)
    except Exception as e:
        print(f"[ERROR] Geometry import failed: {e}")
        return 2

    existing_room_ids = {r.id for r in project.geometry.rooms}
    existing_surface_ids = {s.id for s in project.geometry.surfaces}

    rooms_added = 0
    for room in res.rooms:
        rid = room.id
        if rid in existing_room_ids:
            rid = f"{rid}_{uuid.uuid4().hex[:8]}"
        room.id = rid
        project.geometry.rooms.append(room)
        existing_room_ids.add(rid)
        rooms_added += 1

    surfaces_added = 0
    for s in res.surfaces:
        sid = s.id
        if sid in existing_surface_ids:
            sid = f"{sid}_{uuid.uuid4().hex[:8]}"
        s.id = sid
        project.geometry.surfaces.append(s)
        existing_surface_ids.add(sid)
        surfaces_added += 1

    save_project_schema(project, project_path)
    print("Geometry Import")
    print(f"  File: {args.file}")
    print(f"  Format: {res.format}")
    print(f"  Added rooms: {rooms_added}")
    print(f"  Added surfaces: {surfaces_added}")
    for w in res.warnings:
        print(f"  Warning: {w}")
    return 0


def _cmd_geometry_clean(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)

    if not project.geometry.surfaces:
        print("[ERROR] Project has no surfaces to clean.")
        return 2

    cleaned, report = clean_scene_surfaces(
        project.geometry.surfaces,
        snap_tolerance=args.snap_tolerance,
        merge_coplanar=not args.no_merge,
    )
    project.geometry.surfaces = cleaned

    if args.detect_rooms:
        detected = detect_room_volumes_from_surfaces(cleaned)
        existing = {r.id for r in project.geometry.rooms}
        for room in detected:
            if room.id in existing:
                continue
            project.geometry.rooms.append(room)
            existing.add(room.id)

    save_project_schema(project, project_path)
    print("Geometry Clean")
    print(f"  Surfaces: {report.input_surfaces} -> {report.output_surfaces}")
    print(f"  Merged surfaces: {report.merged_surfaces}")
    print(f"  Snapped vertices: {report.snapped_vertices}")
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

    init = sub.add_parser("init", help="Initialize a new Luxera project file (schema v5).")
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
    ag.add_argument("--room-id", default=None)
    ag.add_argument("--zone-id", default=None)
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

    arg = sub.add_parser("add-roadway-grid", help="Add a roadway calculation grid to a project.")
    arg.add_argument("project", help="Path to project JSON")
    arg.add_argument("--id", default=None, help="Optional roadway grid id")
    arg.add_argument("--name", default=None, help="Grid name")
    arg.add_argument("--lane-width", type=float, required=True)
    arg.add_argument("--road-length", type=float, required=True)
    arg.add_argument("--nx", type=int, required=True)
    arg.add_argument("--ny", type=int, required=True)
    arg.add_argument("--origin-x", type=float, default=0.0)
    arg.add_argument("--origin-y", type=float, default=0.0)
    arg.add_argument("--origin-z", type=float, default=0.0)
    arg.add_argument("--num-lanes", type=int, default=1)
    arg.add_argument("--pole-spacing-m", type=float, default=None)
    arg.add_argument("--mounting-height-m", type=float, default=None)
    arg.add_argument("--setback-m", type=float, default=None)
    arg.add_argument("--observer-height-m", type=float, default=1.5)
    arg.set_defaults(func=_cmd_add_roadway_grid)

    acp = sub.add_parser("add-compliance-profile", help="Add a compliance profile (indoor/roadway/emergency/custom).")
    acp.add_argument("project", help="Path to project JSON")
    acp.add_argument("--id", default=None)
    acp.add_argument("--name", required=True)
    acp.add_argument("--domain", choices=["indoor", "roadway", "emergency", "custom"], required=True)
    acp.add_argument("--standard-ref", required=True)
    acp.add_argument("--thresholds", required=True, help='JSON map, e.g. {"avg_min_lux":1.0}')
    acp.add_argument("--notes", default=None)
    acp.set_defaults(func=_cmd_add_compliance_profile)

    app = sub.add_parser("add-profile-presets", help="Add default compliance profile presets.")
    app.add_argument("project", help="Path to project JSON")
    app.set_defaults(func=_cmd_add_profile_presets)

    aj = sub.add_parser("add-job", help="Add a calculation job to a project.")
    aj.add_argument("project", help="Path to project JSON")
    aj.add_argument("--id", default=None, help="Optional job id")
    aj.add_argument("--type", choices=["direct", "radiosity", "roadway", "emergency", "daylight"], default="direct")
    aj.add_argument("--backend", choices=["cpu", "radiance"], default="cpu")
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
    aj.add_argument("--use-occlusion", action="store_true", default=False, help="Enable geometry occlusion for direct jobs")
    aj.add_argument("--no-occlusion", action="store_true", default=False, help="Disable geometry occlusion for direct jobs")
    aj.add_argument("--occlusion-include-room-shell", action="store_true", default=False, help="Use room shell surfaces as occluders")
    aj.add_argument("--occlusion-epsilon", type=float, default=1e-6, help="Ray epsilon for occlusion tests")
    aj.add_argument("--road-class", default="M3", help="Roadway class label (e.g., M3, P2)")
    aj.add_argument("--road-surface-reflectance", type=float, default=0.07)
    aj.add_argument("--observer-height-m", type=float, default=1.5)
    aj.add_argument("--observer-back-offset-m", type=float, default=60.0)
    aj.add_argument("--observer-lateral-positions", default=None, help="Comma-separated lateral positions in meters")
    aj.add_argument("--compliance-profile-id", default=None, help="Optional compliance profile id")
    aj.add_argument("--emergency-mode", choices=["escape_route", "open_area"], default="escape_route")
    aj.add_argument("--target-min-lux", type=float, default=1.0)
    aj.add_argument("--target-uniformity", type=float, default=0.1)
    aj.add_argument("--battery-duration-min", type=float, default=60.0)
    aj.add_argument("--battery-end-factor", type=float, default=0.5)
    aj.add_argument("--battery-curve", choices=["linear", "exponential"], default="linear")
    aj.add_argument("--battery-steps", type=int, default=7)
    aj.add_argument("--daylight-mode", choices=["daylight_factor", "annual_proxy"], default="daylight_factor")
    aj.add_argument("--exterior-horizontal-illuminance-lux", type=float, default=10000.0)
    aj.add_argument("--daylight-factor-percent", type=float, default=2.0)
    aj.add_argument("--daylight-target-lux", type=float, default=300.0)
    aj.add_argument("--annual-hours", type=int, default=8760)
    aj.add_argument("--weather-hourly-lux-file", default=None, help="Optional file with comma/newline-separated hourly exterior lux values")
    aj.add_argument("--daylight-depth-attenuation", type=float, default=2.0)
    aj.add_argument("--sda-threshold-ratio", type=float, default=0.5)
    aj.add_argument("--udi-low-lux", type=float, default=100.0)
    aj.add_argument("--udi-high-lux", type=float, default=2000.0)
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

    cb = sub.add_parser("export-client", help="Export a client bundle zip for a job result.")
    cb.add_argument("project", help="Path to project JSON")
    cb.add_argument("job_id", help="Job id to export")
    cb.add_argument("--out", required=True, help="Output .zip path")
    cb.set_defaults(func=_cmd_export_client)

    bc = sub.add_parser("export-backend-compare", help="Export backend comparison HTML for a job result.")
    bc.add_argument("project", help="Path to project JSON")
    bc.add_argument("job_id", help="Job id to export")
    bc.add_argument("--out", required=True, help="Output .html path")
    bc.set_defaults(func=_cmd_export_backend_compare)

    rr = sub.add_parser("export-roadway-report", help="Export roadway report HTML for a roadway job result.")
    rr.add_argument("project", help="Path to project JSON")
    rr.add_argument("job_id", help="Job id to export")
    rr.add_argument("--out", required=True, help="Output .html path")
    rr.set_defaults(func=_cmd_export_roadway_report)

    cr = sub.add_parser("compare-results", help="Compare two job results and output deltas.")
    cr.add_argument("project", help="Path to project JSON")
    cr.add_argument("job_a", help="Reference job id")
    cr.add_argument("job_b", help="Comparison job id")
    cr.add_argument("--out", default=None, help="Optional output JSON path")
    cr.set_defaults(func=_cmd_compare_results)

    phot = sub.add_parser("photometry", help="Photometry tooling.")
    phot_sub = phot.add_subparsers(dest="phot_cmd", required=True)

    pv = phot_sub.add_parser("verify", help="Verify photometry file conventions/sanity/hash.")
    pv.add_argument("file", help="Path to IES/LDT file")
    pv.add_argument("--format", default=None, help="Override format (IES or LDT)")
    pv.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    pv.set_defaults(func=_cmd_photometry_verify)

    geom = sub.add_parser("geometry", help="Geometry import/clean tooling.")
    geom_sub = geom.add_subparsers(dest="geom_cmd", required=True)

    gi = geom_sub.add_parser("import", help="Import geometry into a project (DXF/OBJ/GLTF/IFC).")
    gi.add_argument("project", help="Path to project JSON")
    gi.add_argument("file", help="Path to geometry file")
    gi.add_argument("--format", default=None, help="Override format: DXF|OBJ|GLTF|IFC")
    gi.add_argument("--dxf-scale", type=float, default=1.0, help="DXF units -> meters scale")
    gi.set_defaults(func=_cmd_geometry_import)

    gc = geom_sub.add_parser("clean", help="Clean project surfaces (normals, gaps, coplanar merge).")
    gc.add_argument("project", help="Path to project JSON")
    gc.add_argument("--snap-tolerance", type=float, default=1e-3, help="Vertex snap tolerance in meters")
    gc.add_argument("--no-merge", action="store_true", help="Disable coplanar merge")
    gc.add_argument("--detect-rooms", action="store_true", help="Detect room volumes from cleaned surfaces")
    gc.set_defaults(func=_cmd_geometry_clean)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
