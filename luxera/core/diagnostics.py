from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np

from luxera.core.errors import ERROR_CODES
from luxera.parser.ies_parser import parse_ies_text
from luxera.parser.ldt_parser import parse_ldt_text
from luxera.project.schema import Project


@dataclass(frozen=True)
class DiagnosticIssue:
    severity: str  # "error", "warning", "info"
    code: str
    message: str
    suggestion: str
    element_id: Optional[str] = None


class ProjectDiagnostics:
    """
    Run a comprehensive diagnostic check on a project before calculation.
    Returns a list of issues with severity and suggestions.
    """

    def check(self, project: Project) -> List[DiagnosticIssue]:
        issues: List[DiagnosticIssue] = []

        rooms = list(project.geometry.rooms)
        has_geometry = bool(rooms or project.geometry.surfaces)
        if not has_geometry:
            issues.append(
                DiagnosticIssue(
                    severity="error",
                    code="PRJ-002",
                    message="Project has no rooms or imported geometry.",
                    suggestion="Add at least one room or import a geometry model before running calculations.",
                )
            )

        if not project.luminaires:
            issues.append(
                DiagnosticIssue(
                    severity="error",
                    code="CAL-001",
                    message=ERROR_CODES["CAL-001"],
                    suggestion="Add at least one luminaire instance to the project.",
                )
            )

        if not project.grids:
            issues.append(
                DiagnosticIssue(
                    severity="error",
                    code="CAL-002",
                    message=ERROR_CODES["CAL-002"],
                    suggestion="Add at least one calculation grid before running a job.",
                )
            )

        issues.extend(self._check_duplicate_luminaire_ids(project))
        issues.extend(self._check_photometry_assets(project))
        issues.extend(self._check_reflectances(project))
        issues.extend(self._check_room_dimensions(project))
        issues.extend(self._check_mounting_heights(project))
        issues.extend(self._check_grids_within_rooms(project))
        issues.extend(self._check_near_field(project))
        issues.extend(self._check_maintenance_factors(project))
        issues.extend(self._check_radiosity_enclosure(project))

        return issues

    def _check_duplicate_luminaire_ids(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        seen: Set[str] = set()
        for lum in project.luminaires:
            if lum.id in seen:
                out.append(
                    DiagnosticIssue(
                        severity="error",
                        code="PRJ-002",
                        message=f"Duplicate luminaire id detected: {lum.id}",
                        suggestion="Ensure all luminaire IDs are unique.",
                        element_id=lum.id,
                    )
                )
            seen.add(lum.id)
        return out

    def _check_photometry_assets(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        assets: Dict[str, object] = {a.id: a for a in project.photometry_assets}

        for lum in project.luminaires:
            asset = assets.get(lum.photometry_asset_id)
            if asset is None:
                out.append(
                    DiagnosticIssue(
                        severity="error",
                        code="PHO-002",
                        message=f"Luminaire {lum.id} references missing photometry asset {lum.photometry_asset_id}.",
                        suggestion="Add the missing photometry asset or reassign the luminaire asset reference.",
                        element_id=lum.id,
                    )
                )
                continue

            # Parse validation only for file-backed assets to keep diagnostics lightweight.
            raw_path = getattr(asset, "path", None)
            fmt = str(getattr(asset, "format", "")).upper()
            if not raw_path:
                continue
            p = Path(raw_path).expanduser()
            if not p.is_absolute() and project.root_dir:
                p = (Path(project.root_dir).expanduser() / p).resolve()
            if not p.exists():
                out.append(
                    DiagnosticIssue(
                        severity="error",
                        code="PHO-002",
                        message=f"Photometry file not found for asset {getattr(asset, 'id', '<unknown>')}: {p}",
                        suggestion="Fix the asset path or embed the photometry data in the project file.",
                        element_id=getattr(asset, "id", None),
                    )
                )
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                if fmt == "IES":
                    parsed = parse_ies_text(text, source_path=p)
                    if parsed.candela is not None:
                        arr = np.asarray(parsed.candela.values_cd_scaled, dtype=float)
                        if np.any(arr < 0):
                            out.append(
                                DiagnosticIssue(
                                    severity="error",
                                    code="PHO-003",
                                    message=f"Negative candela values found in photometry asset {getattr(asset, 'id', '')}.",
                                    suggestion="Use a valid photometry file with non-negative candela values.",
                                    element_id=getattr(asset, "id", None),
                                )
                            )
                elif fmt == "LDT":
                    parsed = parse_ldt_text(text)
                    arr = np.asarray(parsed.candela.values_cd_scaled, dtype=float)
                    if np.any(arr < 0):
                        out.append(
                            DiagnosticIssue(
                                severity="error",
                                code="PHO-003",
                                message=f"Negative candela values found in photometry asset {getattr(asset, 'id', '')}.",
                                suggestion="Use a valid photometry file with non-negative candela values.",
                                element_id=getattr(asset, "id", None),
                            )
                        )
            except Exception as e:
                out.append(
                    DiagnosticIssue(
                        severity="error",
                        code="PHO-001",
                        message=f"Failed to parse photometry asset {getattr(asset, 'id', '<unknown>')}: {e}",
                        suggestion="Re-export the photometry file and re-import it into the project.",
                        element_id=getattr(asset, "id", None),
                    )
                )
        return out

    def _check_reflectances(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        for room in project.geometry.rooms:
            checks = [
                ("floor_reflectance", room.floor_reflectance),
                ("wall_reflectance", room.wall_reflectance),
                ("ceiling_reflectance", room.ceiling_reflectance),
            ]
            for key, val in checks:
                fv = float(val)
                if fv < 0.0 or fv > 1.0:
                    out.append(
                        DiagnosticIssue(
                            severity="warning",
                            code="PRJ-002",
                            message=f"Room {room.id} has out-of-range {key}={fv:.3f}.",
                            suggestion="Use reflectance values in [0.0, 1.0] for physically plausible results.",
                            element_id=room.id,
                        )
                    )
        return out

    def _check_room_dimensions(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        for room in project.geometry.rooms:
            dims = [float(room.width), float(room.length), float(room.height)]
            if any(d <= 0.1 for d in dims) or any(d >= 1000.0 for d in dims):
                out.append(
                    DiagnosticIssue(
                        severity="warning",
                        code="PRJ-002",
                        message=f"Room {room.id} has implausible dimensions ({room.width} x {room.length} x {room.height} m).",
                        suggestion="Confirm room dimensions are in meters and within realistic bounds.",
                        element_id=room.id,
                    )
                )
        return out

    def _check_mounting_heights(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        rooms = project.geometry.rooms
        if not rooms:
            return out
        room = rooms[0]
        room_z0 = float(room.origin[2])
        room_z1 = room_z0 + float(room.height)
        for lum in project.luminaires:
            z = float(lum.transform.position[2])
            if z > room_z1 + 1e-6:
                out.append(
                    DiagnosticIssue(
                        severity="warning",
                        code="PRJ-002",
                        message=f"Luminaire {lum.id} is above the room ceiling (z={z:.2f}m, ceiling={room_z1:.2f}m).",
                        suggestion="Lower the luminaire mounting height or adjust room height.",
                        element_id=lum.id,
                    )
                )
        return out

    def _check_grids_within_rooms(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        if not project.geometry.rooms:
            return out
        room = project.geometry.rooms[0]
        rx0, ry0, _ = room.origin
        rx1 = float(rx0) + float(room.width)
        ry1 = float(ry0) + float(room.length)
        for grid in project.grids:
            gx0, gy0, _ = grid.origin
            gx1 = float(gx0) + float(grid.width)
            gy1 = float(gy0) + float(grid.height)
            outside = gx0 < rx0 or gy0 < ry0 or gx1 > rx1 or gy1 > ry1
            if outside:
                out.append(
                    DiagnosticIssue(
                        severity="warning",
                        code="PRJ-002",
                        message=f"Grid {grid.id} extends outside room boundaries.",
                        suggestion="Move or resize the grid so it lies fully inside the room.",
                        element_id=grid.id,
                    )
                )
        return out

    def _check_near_field(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        if not project.grids or not project.luminaires:
            return out
        grid = project.grids[0]
        if grid.nx <= 0 or grid.ny <= 0:
            return out
        try:
            gx, gy, gz = grid.origin
            cx = float(gx) + 0.5 * float(grid.width)
            cy = float(gy) + 0.5 * float(grid.height)
            calc_point = np.array([cx, cy, float(grid.elevation)], dtype=float)
            for lum in project.luminaires:
                # No loaded photometry in schema, so only check geometric clearance using mounting height.
                lum_pos = np.array(
                    [float(lum.transform.position[0]), float(lum.transform.position[1]), float(lum.transform.position[2])],
                    dtype=float,
                )
                delta_z = abs(float(lum_pos[2] - calc_point[2]))
                if delta_z <= 0.5:
                    out.append(
                        DiagnosticIssue(
                            severity="warning",
                            code="CAL-004",
                            message=f"Luminaire {lum.id} is very close to workplane ({delta_z:.2f}m); near-field effects likely.",
                            suggestion="Enable near-field correction or increase luminaire-to-workplane distance.",
                            element_id=lum.id,
                        )
                    )
        except Exception:
            # Diagnostics should never fail the run because of optional heuristic checks.
            return out
        return out

    def _check_maintenance_factors(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        for lum in project.luminaires:
            mf = float(getattr(lum, "maintenance_factor", 1.0) or 1.0)
            if mf < 0.1 or mf > 1.0:
                out.append(
                    DiagnosticIssue(
                        severity="warning",
                        code="PRJ-002",
                        message=f"Luminaire {lum.id} has unusual maintenance_factor={mf:.3f}.",
                        suggestion="Use maintenance factor in the range 0.1 to 1.0.",
                        element_id=lum.id,
                    )
                )
        return out

    def _check_radiosity_enclosure(self, project: Project) -> List[DiagnosticIssue]:
        out: List[DiagnosticIssue] = []
        needs_radiosity = any(str(j.type) == "radiosity" for j in project.jobs)
        if needs_radiosity and not project.geometry.rooms:
            out.append(
                DiagnosticIssue(
                    severity="warning",
                    code="GEO-003",
                    message="Radiosity job configured but no enclosed room is defined.",
                    suggestion="Define at least one closed room volume for reliable radiosity results.",
                )
            )
        return out
