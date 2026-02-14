from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from luxera.project.schema import (
    Project,
    Geometry,
    MaterialSpec,
    MaterialLibraryEntry,
    PhotometryAsset,
    LuminaireFamily,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    JobResultRef,
    RotationSpec,
    TransformSpec,
    RoomSpec,
    ZoneSpec,
    NoGoZoneSpec,
    SurfaceSpec,
    OpeningSpec,
    ObstructionSpec,
    LevelSpec,
    CoordinateSystemSpec,
    WorkplaneSpec,
    VerticalPlaneSpec,
    ArbitraryPlaneSpec,
    PointSetSpec,
    LineGridSpec,
    GlareViewSpec,
    EscapeRouteSpec,
    RoadwaySpec,
    RoadwayGridSpec,
    ComplianceProfile,
    Symbol2DSpec,
    BlockInstanceSpec,
    SelectionSetSpec,
    LayerSpec,
    ProjectVariant,
    DaylightAnnualSpec,
    DaylightSpec,
    EmergencyModeSpec,
    EmergencySpec,
)
from luxera.geometry.param.model import (
    FootprintHoleParam,
    FootprintParam,
    InstanceParam,
    OpeningParam,
    ParamModel,
    RoomParam,
    SharedWallParam,
    SlabParam,
    WallParam,
    ZoneParam,
)
from luxera.project.migrations import migrate_project


def _unit_scale_to_m(unit: str) -> float:
    u = str(unit).lower()
    if u == "m":
        return 1.0
    if u == "mm":
        return 0.001
    if u == "cm":
        return 0.01
    if u == "ft":
        return 0.3048
    if u == "in":
        return 0.0254
    return 1.0


def _normalize_unit(unit: str) -> str:
    u = str(unit).lower()
    if u in {"m", "meter", "meters"}:
        return "m"
    if u in {"mm", "millimeter", "millimeters"}:
        return "mm"
    if u in {"cm", "centimeter", "centimeters"}:
        return "cm"
    if u in {"ft", "feet", "foot"}:
        return "ft"
    if u in {"in", "inch", "inches"}:
        return "in"
    return "m"


def _rotation_from_dict(d: Dict[str, Any]) -> RotationSpec:
    return RotationSpec(
        type=d["type"],
        euler_deg=tuple(d["euler_deg"]) if d.get("euler_deg") is not None else None,
        aim=tuple(d["aim"]) if d.get("aim") is not None else None,
        up=tuple(d["up"]) if d.get("up") is not None else None,
        matrix=d.get("matrix"),
    )


def _transform_from_dict(d: Dict[str, Any]) -> TransformSpec:
    return TransformSpec(
        position=tuple(d["position"]),
        rotation=_rotation_from_dict(d["rotation"]),
    )


def _project_from_dict(d: Dict[str, Any]) -> Project:
    geometry = d.get("geometry", {})
    layers_payload = d.get("layers")
    param_payload = d.get("param", {})
    return Project(
        schema_version=d.get("schema_version", 1),
        name=d.get("name", ""),
        geometry=Geometry(
            rooms=[
                RoomSpec(**r) for r in geometry.get("rooms", [])
            ],
            zones=[ZoneSpec(**z) for z in geometry.get("zones", [])],
            no_go_zones=[NoGoZoneSpec(**ng) for ng in geometry.get("no_go_zones", [])],
            surfaces=[SurfaceSpec(**s) for s in geometry.get("surfaces", [])],
            openings=[
                OpeningSpec(
                    **{
                        **o,
                        # Backward/forward compatibility for daylight glazing fields.
                        "opening_type": o.get("opening_type", o.get("kind", "window")),
                        "vt": o.get("vt", o.get("visible_transmittance")),
                        "shade_factor": o.get("shade_factor", o.get("shading_factor")),
                    }
                )
                for o in geometry.get("openings", [])
            ],
            obstructions=[ObstructionSpec(**o) for o in geometry.get("obstructions", [])],
            levels=[LevelSpec(**lvl) for lvl in geometry.get("levels", [])],
            coordinate_systems=[
                CoordinateSystemSpec(
                    id=cs["id"],
                    name=cs["name"],
                    origin=tuple(cs.get("origin", (0.0, 0.0, 0.0))),
                    rotation=_rotation_from_dict(cs.get("rotation", {"type": "euler_zyx", "euler_deg": [0.0, 0.0, 0.0]})),
                    units=_normalize_unit(cs.get("units", cs.get("length_unit", "m"))),
                    length_unit=_normalize_unit(cs.get("length_unit", cs.get("units", "m"))),
                    scale_to_meters=float(
                        cs.get(
                            "scale_to_meters",
                            _unit_scale_to_m(cs.get("length_unit", cs.get("units", "m"))),
                        )
                    ),
                )
                for cs in geometry.get("coordinate_systems", [])
            ],
            length_unit=_normalize_unit(geometry.get("length_unit", "m")),  # type: ignore[arg-type]
            scale_to_meters=float(geometry.get("scale_to_meters", _unit_scale_to_m(geometry.get("length_unit", "m")))),
            source_length_unit=geometry.get("source_length_unit"),
            axis_transform_applied=geometry.get("axis_transform_applied"),
        ),
        materials=[MaterialSpec(**m) for m in d.get("materials", [])],
        material_library=[MaterialLibraryEntry(**m) for m in d.get("material_library", [])],
        photometry_assets=[PhotometryAsset(**p) for p in d.get("photometry_assets", [])],
        luminaire_families=[LuminaireFamily(**f) for f in d.get("luminaire_families", [])],
        luminaires=[
            LuminaireInstance(
                id=l["id"],
                name=l.get("name", ""),
                photometry_asset_id=l["photometry_asset_id"],
                transform=_transform_from_dict(l["transform"]),
                maintenance_factor=l.get("maintenance_factor", 1.0),
                flux_multiplier=l.get("flux_multiplier", 1.0),
                tilt_deg=l.get("tilt_deg", 0.0),
                family_id=l.get("family_id"),
                mounting_type=l.get("mounting_type"),
                mounting_height_m=l.get("mounting_height_m"),
                layer_id=l.get("layer_id"),
                tags=[str(x) for x in l.get("tags", [])] if isinstance(l.get("tags"), list) else [],
            )
            for l in d.get("luminaires", [])
        ],
        grids=[CalcGrid(**g) for g in d.get("grids", [])],
        workplanes=[WorkplaneSpec(**w) for w in d.get("workplanes", [])],
        vertical_planes=[VerticalPlaneSpec(**vp) for vp in d.get("vertical_planes", [])],
        arbitrary_planes=[ArbitraryPlaneSpec(**ap) for ap in d.get("arbitrary_planes", [])],
        point_sets=[PointSetSpec(**ps) for ps in d.get("point_sets", [])],
        line_grids=[LineGridSpec(**lg) for lg in d.get("line_grids", [])],
        glare_views=[GlareViewSpec(**gv) for gv in d.get("glare_views", [])],
        roadways=[RoadwaySpec(**rw) for rw in d.get("roadways", [])],
        roadway_grids=[RoadwayGridSpec(**rg) for rg in d.get("roadway_grids", [])],
        compliance_profiles=[ComplianceProfile(**cp) for cp in d.get("compliance_profiles", [])],
        symbols_2d=[Symbol2DSpec(**s) for s in d.get("symbols_2d", [])],
        block_instances=[BlockInstanceSpec(**b) for b in d.get("block_instances", [])],
        selection_sets=[SelectionSetSpec(**s) for s in d.get("selection_sets", [])],
        layers=[LayerSpec(**layer) for layer in layers_payload] if isinstance(layers_payload, list) and layers_payload else [
            LayerSpec(id="room", name="Rooms", visible=True, order=10),
            LayerSpec(id="wall", name="Walls", visible=True, order=20),
            LayerSpec(id="ceiling_grid", name="Ceiling Grid", visible=True, order=30),
            LayerSpec(id="opening", name="Openings", visible=True, order=40),
            LayerSpec(id="luminaire", name="Luminaires", visible=True, order=50),
            LayerSpec(id="grid", name="Calc Grids", visible=True, order=60),
            LayerSpec(id="symbol", name="Symbols", visible=True, order=70),
        ],
        variants=[ProjectVariant(**v) for v in d.get("variants", [])],
        active_variant_id=d.get("active_variant_id"),
        # Normalize nested daylight/emergency payloads when present in job rows.
        jobs=[
            JobSpec(
                **{
                    **j,
                    "daylight": (
                        DaylightSpec(
                            **{
                                **j["daylight"],
                                "annual": (
                                    DaylightAnnualSpec(**j["daylight"]["annual"])
                                    if isinstance(j["daylight"].get("annual"), dict)
                                    else j["daylight"].get("annual")
                                ),
                            }
                        )
                        if isinstance(j, dict) and isinstance(j.get("daylight"), dict)
                        else j.get("daylight")
                    ),
                    "mode": (
                        EmergencyModeSpec(
                            **{
                                **j["mode"],
                                "include_luminaire_ids": (
                                    list(j["mode"].get("include_luminaire_ids", []))
                                    or list(j["mode"].get("include_luminaires", []))
                                ),
                            }
                        )
                        if isinstance(j, dict) and isinstance(j.get("mode"), dict)
                        else j.get("mode")
                    ),
                    "emergency": EmergencySpec(**j["emergency"]) if isinstance(j, dict) and isinstance(j.get("emergency"), dict) else j.get("emergency"),
                }
            )
            for j in d.get("jobs", [])
        ],
        results=[JobResultRef(**r) for r in d.get("results", [])],
        root_dir=d.get("root_dir"),
        asset_bundle_path=d.get("asset_bundle_path"),
        agent_history=d.get("agent_history", []),
        assistant_undo_stack=d.get("assistant_undo_stack", []),
        assistant_redo_stack=d.get("assistant_redo_stack", []),
        param=ParamModel(
            footprints=[
                FootprintParam(
                    id=str(x["id"]),
                    polygon2d=[(float(p[0]), float(p[1])) for p in x.get("polygon2d", [])],
                    vertex_ids=[str(v) for v in x.get("vertex_ids", [])],
                    edge_ids=[str(e) for e in x.get("edge_ids", [])],
                    holes=[
                        FootprintHoleParam(
                            id=str(h.get("id", "")),
                            polygon2d=[(float(p[0]), float(p[1])) for p in h.get("polygon2d", [])],
                            vertex_ids=[str(v) for v in h.get("vertex_ids", [])],
                            edge_ids=[str(e) for e in h.get("edge_ids", [])],
                        )
                        for h in x.get("holes", [])
                    ],
                    edge_bulges={str(k): float(v) for k, v in dict(x.get("edge_bulges", {})).items()},
                )
                for x in param_payload.get("footprints", [])
            ],
            rooms=[
                RoomParam(
                    id=str(x["id"]),
                    footprint_id=str(x["footprint_id"]),
                    height=float(x["height"]),
                    wall_thickness=float(x.get("wall_thickness", 0.2)),
                    wall_thickness_policy=str(x.get("wall_thickness_policy", x.get("wall_align_mode", "center"))),  # type: ignore[arg-type]
                    wall_align_mode=str(x.get("wall_align_mode", "center")),  # type: ignore[arg-type]
                    name=str(x.get("name", "")),
                    origin_z=float(x.get("origin_z", 0.0)),
                    floor_slab_thickness=float(x.get("floor_slab_thickness", 0.0)),
                    ceiling_slab_thickness=float(x.get("ceiling_slab_thickness", 0.0)),
                    floor_offset=float(x.get("floor_offset", 0.0)),
                    ceiling_offset=float(x.get("ceiling_offset", 0.0)),
                    polygon2d=[(float(p[0]), float(p[1])) for p in x.get("polygon2d", [])],
                )
                for x in param_payload.get("rooms", [])
            ],
            walls=[
                WallParam(
                    id=str(x["id"]),
                    room_id=str(x["room_id"]),
                    edge_ref=(int(x.get("edge_ref", [0, 0])[0]), int(x.get("edge_ref", [0, 0])[1])),
                    edge_id=(str(x["edge_id"]) if x.get("edge_id") is not None else None),
                    shared_edge_id=(str(x["shared_edge_id"]) if x.get("shared_edge_id") is not None else None),
                    thickness=float(x.get("thickness", 0.2)),
                    align_mode=str(x.get("align_mode", "center")),  # type: ignore[arg-type]
                    finish_thickness=float(x.get("finish_thickness", 0.0)),
                    height=(float(x["height"]) if x.get("height") is not None else None),
                    name=str(x.get("name", "")),
                )
                for x in param_payload.get("walls", [])
            ],
            shared_walls=[
                SharedWallParam(
                    id=str(x["id"]),
                    shared_edge_id=(str(x["shared_edge_id"]) if x.get("shared_edge_id") is not None else None),
                    edge_geom=(
                        (float(x.get("edge_geom", [[0.0, 0.0], [0.0, 0.0]])[0][0]), float(x.get("edge_geom", [[0.0, 0.0], [0.0, 0.0]])[0][1])),
                        (float(x.get("edge_geom", [[0.0, 0.0], [0.0, 0.0]])[1][0]), float(x.get("edge_geom", [[0.0, 0.0], [0.0, 0.0]])[1][1])),
                    ),
                    room_a=str(x["room_a"]),
                    room_b=(str(x["room_b"]) if x.get("room_b") is not None else None),
                    thickness=float(x.get("thickness", 0.2)),
                    align_mode=str(x.get("align_mode", "center")),  # type: ignore[arg-type]
                    height=(float(x["height"]) if x.get("height") is not None else None),
                    name=str(x.get("name", "")),
                    wall_material_side_a=(str(x["wall_material_side_a"]) if x.get("wall_material_side_a") is not None else None),
                    wall_material_side_b=(str(x["wall_material_side_b"]) if x.get("wall_material_side_b") is not None else None),
                )
                for x in param_payload.get("shared_walls", [])
            ],
            openings=[
                OpeningParam(
                    id=str(x["id"]),
                    wall_id=str(x["wall_id"]),
                    host_wall_id=(str(x["host_wall_id"]) if x.get("host_wall_id") is not None else None),
                    anchor=float(x.get("anchor", 0.5)),
                    anchor_mode=str(x.get("anchor_mode", "center_at_fraction")),  # type: ignore[arg-type]
                    from_start_distance=(float(x["from_start_distance"]) if x.get("from_start_distance") is not None else None),
                    from_end_distance=(float(x["from_end_distance"]) if x.get("from_end_distance") is not None else None),
                    center_at_fraction=(float(x["center_at_fraction"]) if x.get("center_at_fraction") is not None else None),
                    snap_to_nearest=bool(x.get("snap_to_nearest", False)),
                    gridline_spacing=(float(x["gridline_spacing"]) if x.get("gridline_spacing") is not None else None),
                    spacing_group_id=(str(x["spacing_group_id"]) if x.get("spacing_group_id") is not None else None),
                    width=float(x.get("width", 1.0)),
                    height=float(x.get("height", 1.2)),
                    sill=float(x.get("sill", 0.9)),
                    polygon2d=[(float(p[0]), float(p[1])) for p in x.get("polygon2d", [])],
                    type=str(x.get("type", "window")),  # type: ignore[arg-type]
                    glazing_material_id=(str(x["glazing_material_id"]) if x.get("glazing_material_id") is not None else None),
                    visible_transmittance=(float(x["visible_transmittance"]) if x.get("visible_transmittance") is not None else None),
                )
                for x in param_payload.get("openings", [])
            ],
            slabs=[
                SlabParam(
                    id=str(x["id"]),
                    room_id=str(x["room_id"]),
                    thickness=float(x.get("thickness", 0.2)),
                    elevation=float(x.get("elevation", 0.0)),
                )
                for x in param_payload.get("slabs", [])
            ],
            zones=[
                ZoneParam(
                    id=str(x["id"]),
                    room_id=str(x["room_id"]),
                    polygon2d=[(float(p[0]), float(p[1])) for p in x.get("polygon2d", [])],
                    holes2d=[[(float(p[0]), float(p[1])) for p in hole] for hole in x.get("holes2d", [])],
                    rule_pack_id=(str(x["rule_pack_id"]) if x.get("rule_pack_id") is not None else None),
                )
                for x in param_payload.get("zones", [])
            ],
            instances=[
                InstanceParam(
                    id=str(x["id"]),
                    symbol_id=str(x["symbol_id"]),
                    position=tuple(float(v) for v in x.get("position", (0.0, 0.0, 0.0))),  # type: ignore[arg-type]
                    rotation_deg=tuple(float(v) for v in x.get("rotation_deg", (0.0, 0.0, 0.0))),  # type: ignore[arg-type]
                    scale=tuple(float(v) for v in x.get("scale", (1.0, 1.0, 1.0))),  # type: ignore[arg-type]
                    room_id=(str(x["room_id"]) if x.get("room_id") is not None else None),
                )
                for x in param_payload.get("instances", [])
            ],
        ),
        escape_routes=[EscapeRouteSpec(**er) for er in d.get("escape_routes", [])],
    )


def save_project_schema(project: Project, path: Path) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


def load_project_schema(path: Path) -> Project:
    path = path.expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    data = migrate_project(data)
    project = _project_from_dict(data)
    project.root_dir = str(path.parent)
    return project
