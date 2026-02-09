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
)
from luxera.project.migrations import migrate_project


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
    return Project(
        schema_version=d.get("schema_version", 1),
        name=d.get("name", ""),
        geometry=Geometry(
            rooms=[
                RoomSpec(**r) for r in d.get("geometry", {}).get("rooms", [])
            ]
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
            )
            for l in d.get("luminaires", [])
        ],
        grids=[CalcGrid(**g) for g in d.get("grids", [])],
        jobs=[JobSpec(**j) for j in d.get("jobs", [])],
        results=[JobResultRef(**r) for r in d.get("results", [])],
        root_dir=d.get("root_dir"),
        asset_bundle_path=d.get("asset_bundle_path"),
        agent_history=d.get("agent_history", []),
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
