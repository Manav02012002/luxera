"""
Luxera DXF Import Module

Imports floor plans from DXF (Drawing Exchange Format) files.
DXF is the standard CAD interchange format supported by AutoCAD,
and is commonly used to share floor plans with lighting designers.

This module extracts:
- Room boundaries (closed polylines)
- Furniture objects
- Reference geometry

Supported DXF versions: R12, R14, 2000-2018
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Iterator
from pathlib import Path
import re

from luxera.geometry.core import Vector3, Polygon, Room, MATERIALS


@dataclass
class DXFEntity:
    """Base class for DXF entities."""
    layer: str = "0"
    color: int = 256  # ByLayer


@dataclass
class DXFLine(DXFEntity):
    """A line entity."""
    start: Vector3 = field(default_factory=Vector3.zero)
    end: Vector3 = field(default_factory=Vector3.zero)


@dataclass
class DXFPolyline(DXFEntity):
    """A polyline entity."""
    vertices: List[Vector3] = field(default_factory=list)
    is_closed: bool = False


@dataclass  
class DXFCircle(DXFEntity):
    """A circle entity."""
    center: Vector3 = field(default_factory=Vector3.zero)
    radius: float = 1.0


@dataclass
class DXFArc(DXFEntity):
    """An arc entity."""
    center: Vector3 = field(default_factory=Vector3.zero)
    radius: float = 1.0
    start_angle: float = 0.0  # degrees
    end_angle: float = 360.0  # degrees


@dataclass
class DXFText(DXFEntity):
    """A text entity."""
    position: Vector3 = field(default_factory=Vector3.zero)
    text: str = ""
    height: float = 1.0
    rotation: float = 0.0  # degrees


@dataclass
class DXFInsert(DXFEntity):
    """A block insert (reference)."""
    block_name: str = ""
    position: Vector3 = field(default_factory=Vector3.zero)
    scale: Vector3 = field(default_factory=lambda: Vector3(1, 1, 1))
    rotation: float = 0.0  # degrees


@dataclass
class DXFBlock:
    """A block definition."""
    name: str
    entities: List[DXFEntity] = field(default_factory=list)
    base_point: Vector3 = field(default_factory=Vector3.zero)


@dataclass
class DXFDocument:
    """A parsed DXF document."""
    entities: List[DXFEntity] = field(default_factory=list)
    blocks: Dict[str, DXFBlock] = field(default_factory=dict)
    layers: List[str] = field(default_factory=list)
    units: str = "meters"  # meters, feet, inches, mm
    
    def get_entities_by_layer(self, layer: str) -> List[DXFEntity]:
        """Get all entities on a specific layer."""
        return [e for e in self.entities if e.layer.upper() == layer.upper()]
    
    def get_polylines(self, layer: Optional[str] = None) -> List[DXFPolyline]:
        """Get all polylines, optionally filtered by layer."""
        entities = self.entities if layer is None else self.get_entities_by_layer(layer)
        return [e for e in entities if isinstance(e, DXFPolyline)]
    
    def get_closed_polylines(self, layer: Optional[str] = None) -> List[DXFPolyline]:
        """Get closed polylines (potential room boundaries)."""
        return [p for p in self.get_polylines(layer) if p.is_closed]


class DXFParser:
    """
    Simple DXF parser for extracting geometry.
    
    Note: This is a simplified parser that handles common cases.
    For production use, consider using the ezdxf library.
    """
    
    def __init__(self):
        self.doc = DXFDocument()
        self._current_section = ""
        self._current_entity_type = ""
        self._current_entity_data: Dict[int, str] = {}
        self._current_block: Optional[DXFBlock] = None
        self._in_block = False
    
    def parse_file(self, filepath: Path) -> DXFDocument:
        """Parse a DXF file."""
        with open(filepath, 'r', errors='replace') as f:
            content = f.read()
        return self.parse_string(content)
    
    def parse_string(self, content: str) -> DXFDocument:
        """Parse DXF content from string."""
        self.doc = DXFDocument()
        lines = content.splitlines()
        
        i = 0
        while i < len(lines) - 1:
            try:
                code = int(lines[i].strip())
                value = lines[i + 1].strip()
            except (ValueError, IndexError):
                i += 2
                continue
            
            self._process_pair(code, value)
            i += 2
        
        return self.doc
    
    def _process_pair(self, code: int, value: str):
        """Process a DXF code-value pair."""
        # Section markers
        if code == 0:
            if value == "SECTION":
                pass
            elif value == "ENDSEC":
                self._current_section = ""
            elif value == "EOF":
                pass
            elif self._current_section == "ENTITIES":
                self._flush_entity()
                self._current_entity_type = value
                self._current_entity_data = {}
            elif self._current_section == "BLOCKS":
                if value == "BLOCK":
                    self._current_block = DXFBlock(name="")
                    self._in_block = True
                elif value == "ENDBLK":
                    if self._current_block and self._current_block.name:
                        self.doc.blocks[self._current_block.name] = self._current_block
                    self._current_block = None
                    self._in_block = False
                elif self._in_block:
                    self._flush_entity()
                    self._current_entity_type = value
                    self._current_entity_data = {}
            else:
                self._current_entity_type = value
                self._current_entity_data = {}
        elif code == 2:
            if value in ("HEADER", "TABLES", "BLOCKS", "ENTITIES", "OBJECTS"):
                self._current_section = value
            elif self._current_block is not None:
                self._current_block.name = value
            else:
                self._current_entity_data[code] = value
        else:
            self._current_entity_data[code] = value
    
    def _flush_entity(self):
        """Convert accumulated data into an entity."""
        if not self._current_entity_type or not self._current_entity_data:
            return
        
        entity = self._create_entity()
        if entity:
            if self._in_block and self._current_block:
                self._current_block.entities.append(entity)
            else:
                self.doc.entities.append(entity)
        
        self._current_entity_type = ""
        self._current_entity_data = {}
    
    def _get_float(self, code: int, default: float = 0.0) -> float:
        """Get float value from entity data."""
        if code in self._current_entity_data:
            try:
                return float(self._current_entity_data[code])
            except ValueError:
                pass
        return default
    
    def _get_int(self, code: int, default: int = 0) -> int:
        """Get int value from entity data."""
        if code in self._current_entity_data:
            try:
                return int(self._current_entity_data[code])
            except ValueError:
                pass
        return default
    
    def _get_str(self, code: int, default: str = "") -> str:
        """Get string value from entity data."""
        return self._current_entity_data.get(code, default)
    
    def _create_entity(self) -> Optional[DXFEntity]:
        """Create entity from current data."""
        layer = self._get_str(8, "0")
        color = self._get_int(62, 256)
        
        if self._current_entity_type == "LINE":
            return DXFLine(
                layer=layer,
                color=color,
                start=Vector3(
                    self._get_float(10),
                    self._get_float(20),
                    self._get_float(30),
                ),
                end=Vector3(
                    self._get_float(11),
                    self._get_float(21),
                    self._get_float(31),
                ),
            )
        
        elif self._current_entity_type == "CIRCLE":
            return DXFCircle(
                layer=layer,
                color=color,
                center=Vector3(
                    self._get_float(10),
                    self._get_float(20),
                    self._get_float(30),
                ),
                radius=self._get_float(40, 1.0),
            )
        
        elif self._current_entity_type == "ARC":
            return DXFArc(
                layer=layer,
                color=color,
                center=Vector3(
                    self._get_float(10),
                    self._get_float(20),
                    self._get_float(30),
                ),
                radius=self._get_float(40, 1.0),
                start_angle=self._get_float(50, 0.0),
                end_angle=self._get_float(51, 360.0),
            )
        
        elif self._current_entity_type == "TEXT":
            return DXFText(
                layer=layer,
                color=color,
                position=Vector3(
                    self._get_float(10),
                    self._get_float(20),
                    self._get_float(30),
                ),
                text=self._get_str(1, ""),
                height=self._get_float(40, 1.0),
                rotation=self._get_float(50, 0.0),
            )
        
        elif self._current_entity_type == "INSERT":
            return DXFInsert(
                layer=layer,
                color=color,
                block_name=self._get_str(2, ""),
                position=Vector3(
                    self._get_float(10),
                    self._get_float(20),
                    self._get_float(30),
                ),
                scale=Vector3(
                    self._get_float(41, 1.0),
                    self._get_float(42, 1.0),
                    self._get_float(43, 1.0),
                ),
                rotation=self._get_float(50, 0.0),
            )
        
        elif self._current_entity_type in ("LWPOLYLINE", "POLYLINE"):
            # Simplified polyline handling
            # Full implementation would accumulate VERTEX entities
            vertices = []
            is_closed = self._get_int(70, 0) & 1 == 1
            
            # For LWPOLYLINE, vertices are in pairs of 10,20 codes
            # This is simplified - real implementation needs state machine
            
            return DXFPolyline(
                layer=layer,
                color=color,
                vertices=vertices,
                is_closed=is_closed,
            )
        
        return None


# =============================================================================
# Room Extraction
# =============================================================================

def extract_rooms_from_dxf(
    doc: DXFDocument,
    room_layer: str = "ROOMS",
    default_height: float = 2.8,
    scale: float = 1.0,  # DXF units to meters
) -> List[Room]:
    """
    Extract room definitions from a DXF document.
    
    Looks for closed polylines on the specified layer and converts
    them to Room objects.
    
    Args:
        doc: Parsed DXF document
        room_layer: Layer name containing room boundaries
        default_height: Default room height in meters
        scale: Scale factor to convert DXF units to meters
    
    Returns:
        List of Room objects
    """
    rooms = []
    
    # Find closed polylines on room layer
    polylines = doc.get_closed_polylines(room_layer)
    
    # Also try common layer name variations
    if not polylines:
        for layer in ["ROOM", "ROOMS", "A-ROOM", "A-WALLS", "WALLS"]:
            polylines = doc.get_closed_polylines(layer)
            if polylines:
                break
    
    # If still nothing, use all closed polylines
    if not polylines:
        polylines = doc.get_closed_polylines()
    
    for i, poly in enumerate(polylines):
        if len(poly.vertices) < 3:
            continue
        
        # Scale vertices
        floor_verts = [
            Vector3(v.x * scale, v.y * scale, 0)
            for v in poly.vertices
        ]
        
        room = Room(
            name=f"Room_{i+1}",
            floor_vertices=floor_verts,
            height=default_height,
        )
        rooms.append(room)
    
    return rooms


def load_dxf(filepath: Path) -> DXFDocument:
    """
    Load and parse a DXF file.
    
    Args:
        filepath: Path to DXF file
    
    Returns:
        Parsed DXFDocument
    """
    parser = DXFParser()
    return parser.parse_file(filepath)


# =============================================================================
# Polyline Builder (for creating closed polylines from lines)
# =============================================================================

def lines_to_polylines(lines: List[DXFLine], tolerance: float = 0.01) -> List[DXFPolyline]:
    """
    Convert a set of lines into connected polylines.
    
    This is useful when room boundaries are drawn as individual lines
    rather than polylines.
    
    Args:
        lines: List of line entities
        tolerance: Distance tolerance for connecting endpoints
    
    Returns:
        List of polylines (some may be closed)
    """
    if not lines:
        return []
    
    polylines = []
    used = set()
    
    def find_connected(point: Vector3, exclude: int) -> Optional[Tuple[int, bool]]:
        """Find a line connected to the given point."""
        for i, line in enumerate(lines):
            if i in used or i == exclude:
                continue
            
            if (line.start - point).length() < tolerance:
                return (i, False)  # Connect at start
            if (line.end - point).length() < tolerance:
                return (i, True)  # Connect at end (reversed)
        
        return None
    
    for start_idx, start_line in enumerate(lines):
        if start_idx in used:
            continue
        
        # Start a new polyline
        vertices = [start_line.start, start_line.end]
        used.add(start_idx)
        
        # Extend forward
        while True:
            result = find_connected(vertices[-1], -1)
            if result is None:
                break
            
            idx, reversed_dir = result
            used.add(idx)
            
            if reversed_dir:
                vertices.append(lines[idx].start)
            else:
                vertices.append(lines[idx].end)
        
        # Extend backward
        while True:
            result = find_connected(vertices[0], -1)
            if result is None:
                break
            
            idx, reversed_dir = result
            used.add(idx)
            
            if reversed_dir:
                vertices.insert(0, lines[idx].end)
            else:
                vertices.insert(0, lines[idx].start)
        
        # Check if closed
        is_closed = (vertices[0] - vertices[-1]).length() < tolerance
        if is_closed and len(vertices) > 1:
            vertices = vertices[:-1]  # Remove duplicate endpoint
        
        poly = DXFPolyline(
            vertices=vertices,
            is_closed=is_closed,
            layer=start_line.layer,
        )
        polylines.append(poly)
    
    return polylines
