from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path
from typing import List

from luxera.parser.pipeline import parse_and_analyse_ies
from luxera.plotting.plots import save_default_plots
from luxera.export.pdf_report import build_pdf_report
from luxera.project.io import load_project_schema, save_project_schema
from luxera.project.validator import validate_project_for_job, ProjectValidationError
from luxera.project.schema import (
    Project,
    PhotometryAsset,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    TransformSpec,
    RotationSpec,
    RoomSpec,
    RoadwaySpec,
    RoadwayGridSpec,
    ComplianceProfile,
    DaylightAnnualSpec,
    DaylightSpec,
    EmergencyModeSpec,
    EmergencySpec,
    EscapeRouteSpec,
)
from luxera.project.presets import en12464_direct_job, en13032_radiosity_job, default_compliance_profiles
from luxera.core.hashing import sha256_file
from luxera.photometry.verify import verify_photometry_file
from luxera.io.import_pipeline import run_import_pipeline
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
    horizontal_plane_deg = float(args.horizontal_plane) if args.horizontal_plane is not None else None

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

    paths = save_default_plots(res.doc, outdir, stem=stem, horizontal_plane_deg=horizontal_plane_deg)

    pdf_path = None
    if make_pdf:
        pdf_path = outdir / f"{stem}_report.pdf"
        build_pdf_report(res, paths, pdf_path, source_file=ies_path)

    print("Luxera View")
    print(f"  File: {ies_path}")
    print(f"  Saved: {paths.intensity_png}")
    print(f"  Saved: {paths.polar_png}")
    if horizontal_plane_deg is not None:
        print(f"  Horizontal plane: C={horizontal_plane_deg:g}° (nearest available plane used)")
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
        roadway_id=args.roadway_id,
        num_lanes=args.num_lanes,
        longitudinal_points=args.longitudinal_points,
        transverse_points_per_lane=args.transverse_points_per_lane,
        pole_spacing_m=args.pole_spacing_m,
        mounting_height_m=args.mounting_height_m,
        setback_m=args.setback_m,
        observer_height_m=args.observer_height_m,
    )
    project.roadway_grids.append(rg)
    save_project_schema(project, project_path)
    print(f"Added roadway grid: {rg_id}")
    return 0


def _cmd_add_roadway(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    rw_id = args.id or str(uuid.uuid4())
    roadway = RoadwaySpec(
        id=rw_id,
        name=args.name or f"Roadway {rw_id[:8]}",
        start=(args.start_x, args.start_y, args.start_z),
        end=(args.end_x, args.end_y, args.end_z),
        num_lanes=args.num_lanes,
        lane_width=args.lane_width,
        mounting_height_m=args.mounting_height_m,
        setback_m=args.setback_m,
        pole_spacing_m=args.pole_spacing_m,
        tilt_deg=args.tilt_deg,
        aim_deg=args.aim_deg,
    )
    project.roadways.append(roadway)
    save_project_schema(project, project_path)
    print(f"Added roadway: {rw_id}")
    return 0


def _cmd_add_escape_route(args: argparse.Namespace) -> int:
    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    rid = args.id or str(uuid.uuid4())
    points: List[tuple[float, float, float]] = []
    raw = str(args.polyline).strip()
    for token in raw.split(";"):
        token = token.strip()
        if not token:
            continue
        parts = [x.strip() for x in token.split(",") if x.strip()]
        if len(parts) not in {2, 3}:
            print(f"[ERROR] Invalid polyline point: {token}")
            return 2
        x = float(parts[0])
        y = float(parts[1])
        z = float(parts[2]) if len(parts) == 3 else float(args.height_m)
        points.append((x, y, z))
    if len(points) < 2:
        print("[ERROR] Escape route requires at least two polyline points")
        return 2
    route = EscapeRouteSpec(
        id=rid,
        name=args.name or rid,
        polyline=points,
        width_m=float(args.width_m),
        height_m=float(args.height_m),
        spacing_m=float(args.spacing_m),
        end_margin_m=float(args.end_margin_m),
    )
    project.escape_routes.append(route)
    save_project_schema(project, project_path)
    print(f"Added escape route: {rid}")
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
        daylight_spec = None
        emergency_spec = None
        mode_spec = None
        route_ids: List[str] = []
        open_targets: List[str] = []
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
                emergency_spec = EmergencySpec(
                    standard=args.emergency_standard,  # type: ignore[arg-type]
                    route_min_lux=args.route_min_lux,
                    route_u0_min=args.route_u0_min,
                    open_area_min_lux=args.open_area_min_lux,
                    open_area_u0_min=args.open_area_u0_min,
                )
                mode_spec = EmergencyModeSpec(
                    emergency_factor=args.emergency_factor,
                    include_luminaires=[x for x in args.include_luminaires.split(",") if x.strip()] if args.include_luminaires else [],
                    exclude_luminaires=[x for x in args.exclude_luminaires.split(",") if x.strip()] if args.exclude_luminaires else [],
                )
                route_ids = [x for x in args.routes.split(",") if x.strip()] if args.routes else []
                open_targets = [x for x in args.open_area_targets.split(",") if x.strip()] if args.open_area_targets else []
            else:
                emergency_spec = None
                mode_spec = None
                route_ids = []
                open_targets = []
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
            mode_norm = str(args.daylight_mode)
            annual_spec = None
            if mode_norm in {"df", "radiance"}:
                daylight_mode = mode_norm
                settings_mode = "daylight_factor"
            elif mode_norm == "annual":
                daylight_mode = "annual"
                settings_mode = "annual"
                annual_spec = DaylightAnnualSpec(
                    weather_file=args.daylight_weather_file,
                    occupancy_schedule=args.daylight_occupancy_schedule or "office_8_to_18",
                    grid_targets=[g.id for g in project.grids],
                    sda_target_lux=args.daylight_target_lux,
                    sda_target_percent=50.0,
                    ase_threshold_lux=1000.0,
                    ase_hours_limit=250.0,
                    udi_low=args.udi_low_lux,
                    udi_high=args.udi_high_lux,
                )
            elif mode_norm == "annual_proxy":
                daylight_mode = "df"
                settings_mode = "annual_proxy"
            else:
                daylight_mode = "df"
                settings_mode = "daylight_factor"
            settings = {
                "mode": settings_mode,
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
            daylight_spec = DaylightSpec(
                mode=daylight_mode,  # type: ignore[arg-type]
                sky="CIE_overcast",
                external_horizontal_illuminance_lux=args.exterior_horizontal_illuminance_lux,
                glass_visible_transmittance_default=0.70,
                radiance_quality="normal",
                random_seed=args.seed,
                annual=annual_spec,
            )
        job = JobSpec(
            id=job_id,
            type=args.type,  # type: ignore[arg-type]
            backend=args.backend,  # type: ignore[arg-type]
            settings=settings,
            seed=args.seed,
            daylight=daylight_spec if args.type == "daylight" else None,
            targets=[g.id for g in project.grids] if args.type == "daylight" else [],
            emergency=emergency_spec if args.type == "emergency" else None,
            mode=mode_spec if args.type == "emergency" else None,
            routes=route_ids if args.type == "emergency" else [],
            open_area_targets=open_targets if args.type == "emergency" else [],
        )
    project.jobs.append(job)
    save_project_schema(project, project_path)
    print(f"Added job: {job_id}")
    return 0


def _cmd_run_job(args: argparse.Namespace) -> int:
    from luxera.runner import run_job, RunnerError

    project_path = Path(args.project).expanduser().resolve()
    try:
        ref = run_job(project_path, args.job_id)
    except RunnerError as e:
        print(f"[ERROR] Run failed: {e}")
        return 2
    print(f"Job completed: {ref.job_id}")
    print(f"  Result dir: {ref.result_dir}")
    return 0


def _cmd_daylight(args: argparse.Namespace) -> int:
    from luxera.runner import run_job, RunnerError

    project_path = Path(args.project).expanduser().resolve()
    try:
        ref = run_job(project_path, args.job_id)
    except RunnerError as e:
        print(f"[ERROR] Daylight run failed: {e}")
        return 2
    print(f"Daylight job completed: {ref.job_id}")
    print(f"  Result dir: {ref.result_dir}")
    return 0


def _cmd_run_all(args: argparse.Namespace) -> int:
    from luxera.runner import run_job, RunnerError
    from luxera.export.debug_bundle import export_debug_bundle
    from luxera.export.pdf_report import build_project_pdf_report
    from luxera.export.en12464_report import build_en12464_report_model
    from luxera.export.en12464_pdf import render_en12464_pdf

    project_path = Path(args.project).expanduser().resolve()
    project = load_project_schema(project_path)
    job = next((j for j in project.jobs if j.id == args.job_id), None)
    if job is None:
        print(f"[ERROR] Job not found: {args.job_id}")
        return 2

    try:
        validate_project_for_job(project, job)
    except ProjectValidationError as e:
        print(f"[ERROR] Validation failed:\n{e}")
        return 2

    try:
        ref = run_job(project_path, args.job_id)
    except RunnerError as e:
        print(f"[ERROR] Run failed: {e}")
        return 2
    project = load_project_schema(project_path)
    result_dir = Path(ref.result_dir)

    # Required lightweight summary artifact.
    (result_dir / "summary.json").write_text(json.dumps(ref.summary, indent=2, sort_keys=True), encoding="utf-8")

    # Normalize heatmap naming contract while preserving canonical originals.
    heatmap_src = result_dir / "grid_heatmap.png"
    isolux_src = result_dir / "grid_isolux.png"
    if heatmap_src.exists():
        shutil.copyfile(heatmap_src, result_dir / "heatmap.png")
    if isolux_src.exists():
        shutil.copyfile(isolux_src, result_dir / "isolux.png")

    if args.report:
        out_pdf = result_dir / "report.pdf"
        if job.type in {"roadway", "daylight", "emergency"}:
            build_project_pdf_report(project, ref, out_pdf)
        else:
            model = build_en12464_report_model(project, ref)
            render_en12464_pdf(model, out_pdf)

    if args.bundle:
        out_bundle = result_dir / "audit_bundle.zip"
        export_debug_bundle(project, ref, out_bundle)

    print(f"Run-all completed: {ref.job_id}")
    print(f"  Result dir: {result_dir}")
    if args.report:
        print(f"  Report: {result_dir / 'report.pdf'}")
    if args.bundle:
        print(f"  Audit bundle: {result_dir / 'audit_bundle.zip'}")
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


def _cmd_compare_variants(args: argparse.Namespace) -> int:
    from luxera.project.variants import run_job_for_variants

    project_path = Path(args.project).expanduser().resolve()
    variant_ids = [x.strip() for x in str(args.variants).split(",") if x.strip()]
    if not variant_ids:
        print("[ERROR] Provide at least one variant id in --variants")
        return 2
    baseline = str(args.baseline).strip() if getattr(args, "baseline", None) else None
    try:
        out = run_job_for_variants(project_path, args.job_id, variant_ids, baseline_variant_id=baseline)
    except Exception as e:
        print(f"[ERROR] Variant compare failed: {e}")
        return 2
    print(f"Variant compare JSON: {out.compare_json}")
    print(f"Variant compare CSV: {out.compare_csv}")
    return 0


def _cmd_golden_run(args: argparse.Namespace) -> int:
    from luxera.testing.golden import discover_golden_cases, load_golden_case, run_golden_case

    root = Path(args.root).expanduser().resolve() if args.root else None
    if args.case_id == "all":
        cases = discover_golden_cases(root=root)
    else:
        cases = [load_golden_case(args.case_id, root=root)]
    if not cases:
        print("[ERROR] No golden cases found.")
        return 2
    run_root = Path(args.out).expanduser().resolve() if args.out else None
    for case in cases:
        out = run_golden_case(case, run_root=run_root)
        print(f"Golden run: {case.case_id} -> {out}")
    return 0


def _cmd_golden_compare(args: argparse.Namespace) -> int:
    from luxera.testing.compare import compare_golden_case
    from luxera.testing.golden import discover_golden_cases, load_golden_case, run_golden_case

    root = Path(args.root).expanduser().resolve() if args.root else None
    if args.case_id == "all":
        cases = discover_golden_cases(root=root)
    else:
        cases = [load_golden_case(args.case_id, root=root)]
    if not cases:
        print("[ERROR] No golden cases found.")
        return 2
    run_root = Path(args.out).expanduser().resolve() if args.out else None
    any_fail = False
    for case in cases:
        produced = run_golden_case(case, run_root=run_root)
        cmp = compare_golden_case(case, produced)
        status = "PASS" if cmp.passed else "FAIL"
        print(f"Golden compare: {case.case_id} [{status}] report={cmp.report_path}")
        if not cmp.passed:
            any_fail = True
    return 1 if any_fail else 0


def _cmd_golden_update(args: argparse.Namespace) -> int:
    from luxera.testing.golden import discover_golden_cases, load_golden_case, run_golden_case
    import luxera

    if not args.yes:
        print("[ERROR] Refusing to update golden expected outputs without --yes")
        return 2
    root = Path(args.root).expanduser().resolve() if args.root else None
    if args.case_id == "all":
        cases = discover_golden_cases(root=root)
    else:
        cases = [load_golden_case(args.case_id, root=root)]
    if not cases:
        print("[ERROR] No golden cases found.")
        return 2

    run_root = Path(args.out).expanduser().resolve() if args.out else None
    for case in cases:
        produced = run_golden_case(case, run_root=run_root)
        metadata_payload = {
            "case_id": case.case_id,
            "run_settings": dict(case.run_settings),
            "tolerances": dict(case.tolerances),
            "tolerance_policy": str(case.metadata.get("tolerance_policy", "strict")) if isinstance(case.metadata, dict) else "strict",
            "engine_version": getattr(luxera, "__version__", "unknown"),
        }
        if "job_id" not in metadata_payload["run_settings"]:
            metadata_payload["run_settings"]["job_id"] = case.job_id
        if case.expected_dir.exists():
            shutil.rmtree(case.expected_dir)
        case.expected_dir.mkdir(parents=True, exist_ok=True)
        for src in produced.glob("*"):
            if src.is_file():
                shutil.copyfile(src, case.expected_dir / src.name)
        (case.expected_dir / "metadata.json").write_text(
            json.dumps(metadata_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"Golden expected updated: {case.case_id} -> {case.expected_dir}")
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
    ifc_options = {
        "default_window_transmittance": float(args.ifc_window_vt),
        "fallback_room_size": (float(args.ifc_room_width), float(args.ifc_room_length), float(args.ifc_room_height)),
        "source_up_axis": str(args.ifc_source_up_axis),
        "source_handedness": str(args.ifc_source_handedness),
    }
    layer_overrides = {}
    for tok in list(args.layer_map or []):
        if "=" not in tok:
            print(f"[ERROR] Invalid --layer-map entry: {tok} (expected LAYER=role)")
            return 2
        k, v = tok.split("=", 1)
        layer_overrides[k.strip().upper()] = v.strip().lower()
    try:
        pipeline = run_import_pipeline(
            args.file,
            fmt=args.format,
            dxf_scale=args.dxf_scale,
            length_unit=args.length_unit,
            scale_to_meters=args.scale_to_meters,
            ifc_options=ifc_options,
            layer_overrides=layer_overrides or None,
        )
        if pipeline.geometry is None:
            print(f"[ERROR] Geometry import failed: {json.dumps(pipeline.report.to_dict(), indent=2, sort_keys=True)}")
            return 2
        res = pipeline.geometry
    except Exception as e:
        print(f"[ERROR] Geometry import failed: {e}")
        return 2

    existing_room_ids = {r.id for r in project.geometry.rooms}
    existing_surface_ids = {s.id for s in project.geometry.surfaces}
    existing_opening_ids = {o.id for o in project.geometry.openings}
    existing_level_ids = {l.id for l in project.geometry.levels}
    existing_obstruction_ids = {o.id for o in project.geometry.obstructions}

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

    openings_added = 0
    for op in res.openings:
        oid = op.id
        if oid in existing_opening_ids:
            oid = f"{oid}_{uuid.uuid4().hex[:8]}"
        op.id = oid
        project.geometry.openings.append(op)
        existing_opening_ids.add(oid)
        openings_added += 1

    levels_added = 0
    for lvl in res.levels:
        lid = lvl.id
        if lid in existing_level_ids:
            lid = f"{lid}_{uuid.uuid4().hex[:8]}"
        lvl.id = lid
        project.geometry.levels.append(lvl)
        existing_level_ids.add(lid)
        levels_added += 1

    obstructions_added = 0
    for ob in res.obstructions:
        oid = ob.id
        if oid in existing_obstruction_ids:
            oid = f"{oid}_{uuid.uuid4().hex[:8]}"
        ob.id = oid
        project.geometry.obstructions.append(ob)
        existing_obstruction_ids.add(oid)
        obstructions_added += 1

    # Imported geometry coordinates are normalized to meters.
    project.geometry.length_unit = "m"
    project.geometry.scale_to_meters = 1.0

    save_project_schema(project, project_path)
    print("Geometry Import")
    print(f"  File: {args.file}")
    print(f"  Format: {res.format}")
    print(f"  Import length unit: {res.length_unit}")
    print(f"  Import scale_to_meters: {res.scale_to_meters}")
    print(f"  Added rooms: {rooms_added}")
    print(f"  Added surfaces: {surfaces_added}")
    print(f"  Added openings: {openings_added}")
    print(f"  Added levels: {levels_added}")
    print(f"  Added obstructions: {obstructions_added}")
    for w in res.warnings:
        print(f"  Warning: {w}")
    if pipeline.report.layer_map:
        print(f"  Layer map entries: {len(pipeline.report.layer_map)}")
    if pipeline.report.scene_health:
        counts = pipeline.report.scene_health.get("counts", {})
        print(f"  Scene health checks: {len(counts)}")
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
    v.add_argument("--horizontal-plane", type=float, default=None, help="Optional C-plane angle (degrees) for plot selection")
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
    arg.add_argument("--roadway-id", default=None, help="Optional roadway object id")
    arg.add_argument("--num-lanes", type=int, default=1)
    arg.add_argument("--longitudinal-points", type=int, default=None)
    arg.add_argument("--transverse-points-per-lane", type=int, default=None)
    arg.add_argument("--pole-spacing-m", type=float, default=None)
    arg.add_argument("--mounting-height-m", type=float, default=None)
    arg.add_argument("--setback-m", type=float, default=None)
    arg.add_argument("--observer-height-m", type=float, default=1.5)
    arg.set_defaults(func=_cmd_add_roadway_grid)

    arw = sub.add_parser("add-roadway", help="Add a roadway layout object.")
    arw.add_argument("project", help="Path to project JSON")
    arw.add_argument("--id", default=None, help="Optional roadway id")
    arw.add_argument("--name", default=None, help="Roadway name")
    arw.add_argument("--start-x", type=float, required=True)
    arw.add_argument("--start-y", type=float, required=True)
    arw.add_argument("--start-z", type=float, default=0.0)
    arw.add_argument("--end-x", type=float, required=True)
    arw.add_argument("--end-y", type=float, required=True)
    arw.add_argument("--end-z", type=float, default=0.0)
    arw.add_argument("--num-lanes", type=int, default=1)
    arw.add_argument("--lane-width", type=float, default=3.5)
    arw.add_argument("--mounting-height-m", type=float, default=None)
    arw.add_argument("--setback-m", type=float, default=None)
    arw.add_argument("--pole-spacing-m", type=float, default=None)
    arw.add_argument("--tilt-deg", type=float, default=None)
    arw.add_argument("--aim-deg", type=float, default=None)
    arw.set_defaults(func=_cmd_add_roadway)

    aer = sub.add_parser("add-escape-route", help="Add an emergency escape route polyline.")
    aer.add_argument("project", help="Path to project JSON")
    aer.add_argument("--id", default=None, help="Optional route id")
    aer.add_argument("--name", default=None, help="Optional route name")
    aer.add_argument("--polyline", required=True, help='Semicolon separated points "x,y[,z];x,y[,z]"')
    aer.add_argument("--width-m", type=float, default=1.0)
    aer.add_argument("--height-m", type=float, default=0.0)
    aer.add_argument("--spacing-m", type=float, default=0.5)
    aer.add_argument("--end-margin-m", type=float, default=0.0)
    aer.set_defaults(func=_cmd_add_escape_route)

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
    aj.add_argument("--backend", choices=["cpu", "df", "radiance"], default="cpu")
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
    aj.add_argument("--emergency-standard", choices=["EN1838", "BS5266"], default="EN1838")
    aj.add_argument("--emergency-factor", type=float, default=1.0)
    aj.add_argument("--route-min-lux", type=float, default=1.0)
    aj.add_argument("--route-u0-min", type=float, default=0.1)
    aj.add_argument("--open-area-min-lux", type=float, default=0.5)
    aj.add_argument("--open-area-u0-min", type=float, default=0.1)
    aj.add_argument("--include-luminaires", default=None, help="Comma-separated luminaire ids")
    aj.add_argument("--exclude-luminaires", default=None, help="Comma-separated luminaire ids")
    aj.add_argument("--routes", default=None, help="Comma-separated escape route ids")
    aj.add_argument("--open-area-targets", default=None, help="Comma-separated grid ids")
    aj.add_argument("--daylight-mode", choices=["daylight_factor", "annual_proxy", "df", "radiance", "annual"], default="daylight_factor")
    aj.add_argument("--exterior-horizontal-illuminance-lux", type=float, default=10000.0)
    aj.add_argument("--daylight-factor-percent", type=float, default=2.0)
    aj.add_argument("--daylight-target-lux", type=float, default=300.0)
    aj.add_argument("--annual-hours", type=int, default=8760)
    aj.add_argument("--daylight-weather-file", default=None, help="EPW weather file path for annual daylight mode")
    aj.add_argument("--daylight-occupancy-schedule", default="office_8_to_18", help="Occupancy schedule preset or CSV-like weights")
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

    dj = sub.add_parser("daylight", help="Run a daylight job by id.")
    dj.add_argument("project", help="Path to project JSON")
    dj.add_argument("--job", dest="job_id", required=True, help="Daylight job id")
    dj.set_defaults(func=_cmd_daylight)

    ra = sub.add_parser("run-all", help="Validate, run, and optionally generate report and audit bundle.")
    ra.add_argument("project", help="Path to project JSON")
    ra.add_argument("--job", dest="job_id", required=True, help="Job id to run")
    ra.add_argument("--report", action="store_true", help="Generate report.pdf in the result directory")
    ra.add_argument("--bundle", action="store_true", help="Generate audit_bundle.zip in the result directory")
    ra.set_defaults(func=_cmd_run_all)

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

    cv = sub.add_parser("compare-variants", help="Run a job for selected variants and export comparison table.")
    cv.add_argument("project", help="Path to project JSON")
    cv.add_argument("job_id", help="Job id to run for all selected variants")
    cv.add_argument("--variants", required=True, help="Comma-separated variant ids")
    cv.add_argument("--baseline", default=None, help="Optional baseline variant id for delta columns")
    cv.set_defaults(func=_cmd_compare_variants)

    golden = sub.add_parser("golden", help="Golden regression harness tooling.")
    golden_sub = golden.add_subparsers(dest="golden_cmd", required=True)

    gr = golden_sub.add_parser("run", help="Run one golden case (or all) and emit produced artifacts.")
    gr.add_argument("case_id", help="Golden case id or 'all'")
    gr.add_argument("--root", default=None, help="Golden root directory (default: tests/golden)")
    gr.add_argument("--out", default=None, help="Output run root (default: <golden_root>/runs)")
    gr.set_defaults(func=_cmd_golden_run)

    gc = golden_sub.add_parser("compare", help="Run and compare one golden case (or all) against expected.")
    gc.add_argument("case_id", help="Golden case id or 'all'")
    gc.add_argument("--root", default=None, help="Golden root directory (default: tests/golden)")
    gc.add_argument("--out", default=None, help="Output run root (default: <golden_root>/runs)")
    gc.set_defaults(func=_cmd_golden_compare)

    gu = golden_sub.add_parser("update", help="Run and overwrite expected artifacts for one case (or all).")
    gu.add_argument("case_id", help="Golden case id or 'all'")
    gu.add_argument("--root", default=None, help="Golden root directory (default: tests/golden)")
    gu.add_argument("--out", default=None, help="Output run root (default: <golden_root>/runs)")
    gu.add_argument("--yes", action="store_true", help="Required acknowledgement for overwriting expected outputs")
    gu.set_defaults(func=_cmd_golden_update)

    phot = sub.add_parser("photometry", help="Photometry tooling.")
    phot_sub = phot.add_subparsers(dest="phot_cmd", required=True)

    pv = phot_sub.add_parser("verify", help="Verify photometry file conventions/sanity/hash.")
    pv.add_argument("file", help="Path to IES/LDT file")
    pv.add_argument("--format", default=None, help="Override format (IES or LDT)")
    pv.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    pv.set_defaults(func=_cmd_photometry_verify)

    geom = sub.add_parser("geometry", help="Geometry import/clean tooling.")
    geom_sub = geom.add_subparsers(dest="geom_cmd", required=True)

    gi = geom_sub.add_parser("import", help="Import geometry into a project (DXF/OBJ/GLTF/FBX/SKP/IFC/DWG).")
    gi.add_argument("project", help="Path to project JSON")
    gi.add_argument("file", help="Path to geometry file")
    gi.add_argument("--format", default=None, help="Override format: DXF|OBJ|GLTF|FBX|SKP|IFC|DWG")
    gi.add_argument("--dxf-scale", type=float, default=1.0, help="DXF units -> meters scale")
    gi.add_argument("--length-unit", default=None, help="Optional unit override: m|mm|cm|ft|in")
    gi.add_argument("--scale-to-meters", type=float, default=None, help="Optional explicit unit scale")
    gi.add_argument("--ifc-window-vt", type=float, default=0.70, help="IFC default visible transmittance for imported windows")
    gi.add_argument("--ifc-room-width", type=float, default=5.0, help="IFC fallback room width")
    gi.add_argument("--ifc-room-length", type=float, default=5.0, help="IFC fallback room length")
    gi.add_argument("--ifc-room-height", type=float, default=3.0, help="IFC fallback room height")
    gi.add_argument("--ifc-source-up-axis", default="Z_UP", choices=["Z_UP", "Y_UP"], help="IFC source up-axis convention")
    gi.add_argument(
        "--ifc-source-handedness",
        default="RIGHT_HANDED",
        choices=["RIGHT_HANDED", "LEFT_HANDED"],
        help="IFC source handedness convention",
    )
    gi.add_argument(
        "--layer-map",
        action="append",
        default=[],
        help="Layer role override for DXF (repeatable): LAYER=wall|door|window|room|grid|unmapped",
    )
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
