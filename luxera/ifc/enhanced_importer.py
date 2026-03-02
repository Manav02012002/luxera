from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from luxera.project.schema import (
    CoordinateSystemSpec,
    LevelSpec,
    MaterialSpec,
    OpeningSpec,
    Project,
    RoomSpec,
    RotationSpec,
    SurfaceSpec,
)


class EnhancedIFCImporter:
    """
    Enhanced IFC importer that extracts:
    1. IfcSpace entities -> Luxera rooms with dimensions
    2. IfcWall, IfcSlab, IfcRoof -> surfaces with materials
    3. IfcWindow, IfcDoor -> openings (important for daylight and occlusion)
    4. IfcMaterial -> Luxera material library entries with reflectance estimates
    5. IfcBuildingStorey -> storey organization
    6. Coordinate system alignment (project north, true north, elevation)
    """

    def __init__(self, ifc_path: Path):
        """
        Open IFC file using ifcopenshell (import ifcopenshell).
        If ifcopenshell is not installed, raise ImportError with install instructions.
        """
        self.ifc_path = Path(ifc_path).expanduser().resolve()
        if not self.ifc_path.exists():
            raise FileNotFoundError(f"IFC file not found: {self.ifc_path}")
        try:
            import ifcopenshell  # type: ignore
        except Exception as e:
            raise ImportError(
                "EnhancedIFCImporter requires ifcopenshell. Install with: pip install ifcopenshell"
            ) from e

        self._ifcopenshell = ifcopenshell
        self.model = ifcopenshell.open(str(self.ifc_path))

    def import_spaces(self) -> List[Dict[str, Any]]:
        """
        Extract all IfcSpace entities.
        """
        out: List[Dict[str, Any]] = []
        for i, s in enumerate(self.model.by_type("IfcSpace") or []):
            width, length, height = self._extract_dimensions(s, default=(5.0, 5.0, 3.0))
            origin = self._extract_origin(s)
            contained = self._contained_elements(s)
            out.append(
                {
                    "id": self._entity_id(s, f"space_{i+1}"),
                    "name": self._entity_name(s, f"Space {i+1}"),
                    "long_name": getattr(s, "LongName", None),
                    "width": width,
                    "length": length,
                    "height": height,
                    "origin": origin,
                    "contained_elements": contained,
                }
            )
        return out

    def import_surfaces(self) -> List[Dict[str, Any]]:
        """
        Extract wall, floor, ceiling, and roof surfaces.
        """
        out: List[Dict[str, Any]] = []
        for kind, ifc_type in (("wall", "IfcWall"), ("floor", "IfcSlab"), ("ceiling", "IfcRoof")):
            for i, e in enumerate(self.model.by_type(ifc_type) or []):
                w, l, h = self._extract_dimensions(e, default=(4.0, 0.2, 3.0))
                origin = self._extract_origin(e)
                material_name = self._extract_material_name(e)
                reflectance = self._estimate_reflectance(material_name)
                vertices = self._surface_vertices(kind=kind, origin=origin, width=w, length=l, height=h)
                out.append(
                    {
                        "id": self._entity_id(e, f"{ifc_type.lower()}_{i+1}"),
                        "name": self._entity_name(e, f"{ifc_type} {i+1}"),
                        "kind": kind,
                        "vertices": vertices,
                        "material_name": material_name,
                        "reflectance": reflectance,
                    }
                )
        return out

    def import_openings(self) -> List[Dict[str, Any]]:
        """
        Extract windows and doors.
        """
        out: List[Dict[str, Any]] = []

        def _append_openings(ifc_type: str, opening_kind: str) -> None:
            for i, e in enumerate(self.model.by_type(ifc_type) or []):
                w, _, h = self._extract_dimensions(e, default=(1.2, 0.2, 1.2))
                origin = self._extract_origin(e)
                host = self._extract_host_id(e)
                vertices = self._opening_vertices(origin=origin, width=w, height=h)
                out.append(
                    {
                        "id": self._entity_id(e, f"{ifc_type.lower()}_{i+1}"),
                        "name": self._entity_name(e, f"{ifc_type} {i+1}"),
                        "kind": opening_kind,
                        "host_surface_id": host,
                        "origin": origin,
                        "width": w,
                        "height": h,
                        "vertices": vertices,
                    }
                )

        _append_openings("IfcWindow", "window")
        _append_openings("IfcDoor", "door")
        return out

    def _estimate_reflectance(self, material_name: str) -> float:
        """
        Estimate surface reflectance from IFC material name using a lookup table.
        """
        n = str(material_name or "").lower()
        if "concrete" in n:
            return 0.35
        if "plaster" in n or "gypsum" in n:
            return 0.70
        if "carpet" in n:
            return 0.20
        if "timber" in n or "wood" in n:
            return 0.30
        if "glass" in n:
            return 0.10
        if "metal" in n or "steel" in n:
            return 0.50
        if "brick" in n:
            return 0.25
        if "tile" in n or "ceramic" in n:
            return 0.50
        return 0.50

    def to_project(self) -> Project:
        """
        Convert all imported data into a complete Luxera Project schema.
        Includes rooms, surfaces, openings, materials, and storey info.
        """
        project = Project(name=self.ifc_path.stem, root_dir=str(self.ifc_path.parent))

        spaces = self.import_spaces()
        surfaces = self.import_surfaces()
        openings = self.import_openings()

        levels = self._import_storeys()
        project.geometry.levels.extend(levels)

        # Coordinate system alignment metadata (basic defaults + optional extracted headings).
        project.geometry.coordinate_systems.append(
            CoordinateSystemSpec(
                id="ifc_cs_1",
                name="IFC Project CS",
                origin=(0.0, 0.0, 0.0),
                rotation=RotationSpec(type="euler_zyx", euler_deg=(0.0, 0.0, 0.0)),
                units="m",
                length_unit="m",
                scale_to_meters=1.0,
            )
        )

        default_level_id = levels[0].id if levels else None
        for r in spaces:
            project.geometry.rooms.append(
                RoomSpec(
                    id=str(r["id"]),
                    name=str(r["name"]),
                    width=float(r["width"]),
                    length=float(r["length"]),
                    height=float(r["height"]),
                    origin=tuple(float(v) for v in r["origin"]),
                    level_id=default_level_id,
                )
            )

        # Build material library entries from imported materials.
        mat_map: Dict[str, str] = {}
        for s in surfaces:
            mat_name = str(s.get("material_name") or "Unknown")
            mat_id = self._material_id(mat_name)
            if mat_id not in mat_map:
                mat_map[mat_id] = mat_name
                project.materials.append(
                    MaterialSpec(
                        id=mat_id,
                        name=mat_name,
                        reflectance=float(s.get("reflectance", 0.5)),
                        specularity=0.05,
                    )
                )

        first_room_id = project.geometry.rooms[0].id if project.geometry.rooms else None
        for i, s in enumerate(surfaces):
            mat_id = self._material_id(str(s.get("material_name") or "Unknown"))
            project.geometry.surfaces.append(
                SurfaceSpec(
                    id=str(s["id"]),
                    name=str(s["name"]),
                    kind=str(s.get("kind", "custom")),  # type: ignore[arg-type]
                    vertices=[tuple(float(v) for v in p) for p in s.get("vertices", [])],
                    room_id=first_room_id,
                    material_id=mat_id,
                )
            )

        host_default = project.geometry.surfaces[0].id if project.geometry.surfaces else None
        for o in openings:
            kind = str(o.get("kind", "window"))
            project.geometry.openings.append(
                OpeningSpec(
                    id=str(o["id"]),
                    name=str(o["name"]),
                    opening_type=("door" if kind == "door" else "window"),
                    kind=("door" if kind == "door" else "window"),
                    host_surface_id=str(o.get("host_surface_id") or host_default or ""),
                    vertices=[tuple(float(v) for v in p) for p in o.get("vertices", [])],
                    is_daylight_aperture=(kind == "window"),
                    visible_transmittance=(0.65 if kind == "window" else None),
                )
            )

        return project

    def _import_storeys(self) -> List[LevelSpec]:
        out: List[LevelSpec] = []
        for i, s in enumerate(self.model.by_type("IfcBuildingStorey") or []):
            elev = self._float_first(getattr(s, "Elevation", None), default=float(i) * 3.0)
            out.append(
                LevelSpec(
                    id=self._entity_id(s, f"storey_{i+1}"),
                    name=self._entity_name(s, f"Storey {i+1}"),
                    elevation=elev,
                )
            )
        return out

    @staticmethod
    def _entity_id(entity: Any, fallback: str) -> str:
        gid = getattr(entity, "GlobalId", None)
        if gid:
            return str(gid)
        tag = getattr(entity, "Tag", None)
        if tag:
            return str(tag)
        return str(fallback)

    @staticmethod
    def _entity_name(entity: Any, fallback: str) -> str:
        nm = getattr(entity, "Name", None)
        return str(nm) if nm else str(fallback)

    @staticmethod
    def _float_first(value: Any, default: float) -> float:
        try:
            if value is None:
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def _extract_dimensions(self, entity: Any, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
        attrs = {
            "width": getattr(entity, "Width", None),
            "length": getattr(entity, "Length", None),
            "height": getattr(entity, "Height", None),
            "overall_width": getattr(entity, "OverallWidth", None),
            "overall_height": getattr(entity, "OverallHeight", None),
            "xdim": getattr(entity, "XDim", None),
            "ydim": getattr(entity, "YDim", None),
            "zdim": getattr(entity, "ZDim", None),
        }

        width = self._float_first(
            attrs["width"] or attrs["overall_width"] or attrs["xdim"],
            default=default[0],
        )
        length = self._float_first(
            attrs["length"] or attrs["ydim"],
            default=default[1],
        )
        height = self._float_first(
            attrs["height"] or attrs["overall_height"] or attrs["zdim"],
            default=default[2],
        )

        # Try textual fallback for patterns like "12x8x3" in Description.
        desc = str(getattr(entity, "Description", "") or "")
        m = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)", desc)
        if m:
            width, length, height = float(m.group(1)), float(m.group(2)), float(m.group(3))

        return (max(width, 0.1), max(length, 0.1), max(height, 0.1))

    @staticmethod
    def _extract_origin(entity: Any) -> Tuple[float, float, float]:
        for attr in ("Origin", "origin", "Position", "position"):
            v = getattr(entity, attr, None)
            if isinstance(v, (tuple, list)) and len(v) >= 3:
                try:
                    return (float(v[0]), float(v[1]), float(v[2]))
                except Exception:
                    pass

        placement = getattr(entity, "ObjectPlacement", None)
        rel = getattr(placement, "RelativePlacement", None) if placement is not None else None
        loc = getattr(rel, "Location", None) if rel is not None else None
        coords = getattr(loc, "Coordinates", None) if loc is not None else None
        if isinstance(coords, (tuple, list)) and len(coords) >= 3:
            try:
                return (float(coords[0]), float(coords[1]), float(coords[2]))
            except Exception:
                pass

        return (0.0, 0.0, 0.0)

    @staticmethod
    def _contained_elements(space: Any) -> List[str]:
        out: List[str] = []
        rels = getattr(space, "ContainsElements", None) or []
        for rel in rels:
            for elem in (getattr(rel, "RelatedElements", None) or []):
                nm = getattr(elem, "Name", None) or getattr(elem, "GlobalId", None)
                if nm:
                    out.append(str(nm))
        return out

    @staticmethod
    def _extract_material_name(entity: Any) -> str:
        # Common mocked/simple attributes first.
        for attr in ("Material", "material", "MaterialName", "material_name"):
            val = getattr(entity, attr, None)
            if isinstance(val, str) and val.strip():
                return val.strip()
            nm = getattr(val, "Name", None) if val is not None else None
            if nm:
                return str(nm)

        # IFC associations fallback.
        for rel in (getattr(entity, "HasAssociations", None) or []):
            mat = getattr(rel, "RelatingMaterial", None)
            if mat is None:
                continue
            nm = getattr(mat, "Name", None)
            if nm:
                return str(nm)
            for layer in (getattr(mat, "MaterialLayers", None) or []):
                lmat = getattr(layer, "Material", None)
                lnm = getattr(lmat, "Name", None) if lmat is not None else None
                if lnm:
                    return str(lnm)

        return "Unknown"

    @staticmethod
    def _extract_host_id(entity: Any) -> Optional[str]:
        host = getattr(entity, "HostSurfaceId", None)
        if host:
            return str(host)
        for rel in (getattr(entity, "FillsVoids", None) or []):
            opening = getattr(rel, "RelatingOpeningElement", None)
            if opening is None:
                continue
            for rv in (getattr(opening, "VoidsElements", None) or []):
                building = getattr(rv, "RelatingBuildingElement", None)
                gid = getattr(building, "GlobalId", None) if building is not None else None
                if gid:
                    return str(gid)
        return None

    @staticmethod
    def _surface_vertices(*, kind: str, origin: Tuple[float, float, float], width: float, length: float, height: float) -> List[Tuple[float, float, float]]:
        x, y, z = origin
        if kind == "floor":
            return [(x, y, z), (x + width, y, z), (x + width, y + length, z), (x, y + length, z)]
        if kind == "ceiling":
            zz = z + max(height, 0.1)
            return [(x, y, zz), (x + width, y, zz), (x + width, y + length, zz), (x, y + length, zz)]
        # wall-like plane
        return [(x, y, z), (x + width, y, z), (x + width, y, z + height), (x, y, z + height)]

    @staticmethod
    def _opening_vertices(*, origin: Tuple[float, float, float], width: float, height: float) -> List[Tuple[float, float, float]]:
        x, y, z = origin
        return [(x, y, z), (x + width, y, z), (x + width, y, z + height), (x, y, z + height)]

    @staticmethod
    def _material_id(name: str) -> str:
        n = re.sub(r"[^a-zA-Z0-9]+", "_", str(name).strip().lower()).strip("_")
        return f"ifc_mat_{n or 'unknown'}"
