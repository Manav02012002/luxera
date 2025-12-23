"""
Luxera Project File Format

Handles saving and loading of complete Luxera projects (.luxera files).

A Luxera project contains:
- Scene geometry (rooms, surfaces)
- Luminaire placements with IES data references
- Calculation grids and results
- Material assignments
- Compliance settings
- Emergency lighting layout

File format: JSON-based with optional embedded binary data (for IES files).
"""

from __future__ import annotations

import json
import base64
import gzip
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime
import uuid

from luxera.geometry.core import Vector3, Material, Room, Scene, MATERIALS
from luxera.compliance.standards import ActivityType


# =============================================================================
# Project Data Classes
# =============================================================================

@dataclass
class LuminaireReference:
    """Reference to a luminaire in the project."""
    id: str
    name: str
    ies_filename: Optional[str] = None  # Reference to external IES file
    ies_data_embedded: Optional[str] = None  # Base64 encoded IES content
    position: Tuple[float, float, float] = (0, 0, 0)
    rotation: float = 0.0  # Degrees
    aim_vector: Tuple[float, float, float] = (0, 0, -1)
    flux_multiplier: float = 1.0
    is_emergency: bool = False
    emergency_lumens: Optional[float] = None


@dataclass
class RoomData:
    """Serializable room data."""
    id: str
    name: str
    floor_vertices: List[Tuple[float, float]]  # 2D floor polygon
    height: float
    floor_material: str  # Material name from library
    ceiling_material: str
    wall_material: str
    activity_type: Optional[str] = None  # ActivityType name
    
    def to_room(self) -> Room:
        """Convert to Room object."""
        floor_verts = [Vector3(x, y, 0) for x, y in self.floor_vertices]
        
        floor_mat = MATERIALS.get(self.floor_material, MATERIALS['carpet_medium'])
        ceiling_mat = MATERIALS.get(self.ceiling_material, MATERIALS['white_ceiling'])
        wall_mat = MATERIALS.get(self.wall_material, MATERIALS['light_gray'])
        
        return Room(
            name=self.name,
            floor_vertices=floor_verts,
            height=self.height,
            floor_material=floor_mat,
            ceiling_material=ceiling_mat,
            wall_material=wall_mat,
        )
    
    @staticmethod
    def from_room(room: Room, room_id: str = None) -> 'RoomData':
        """Create from Room object."""
        return RoomData(
            id=room_id or str(uuid.uuid4()),
            name=room.name,
            floor_vertices=[(v.x, v.y) for v in room.floor_vertices],
            height=room.height,
            floor_material=room.floor_material.name if hasattr(room.floor_material, 'name') else 'carpet_medium',
            ceiling_material=room.ceiling_material.name if hasattr(room.ceiling_material, 'name') else 'white_ceiling',
            wall_material=room.wall_material.name if hasattr(room.wall_material, 'name') else 'light_gray',
        )


@dataclass
class CalculationSettings:
    """Calculation settings for the project."""
    work_plane_height: float = 0.8  # meters
    grid_spacing: float = 0.5  # meters
    include_interreflections: bool = True
    radiosity_iterations: int = 50
    maintenance_factor: float = 0.8
    
    # Compliance
    target_activity_type: Optional[str] = None
    custom_illuminance_target: Optional[float] = None
    custom_uniformity_target: Optional[float] = None


@dataclass
class ProjectMetadata:
    """Project metadata."""
    name: str
    description: str = ""
    author: str = ""
    company: str = ""
    client: str = ""
    project_number: str = ""
    created_at: str = ""
    modified_at: str = ""
    luxera_version: str = "0.2.0"
    
    def update_modified(self):
        self.modified_at = datetime.now().isoformat()


@dataclass
class LuxeraProject:
    """
    A complete Luxera project.
    
    This is the top-level container for all project data.
    """
    metadata: ProjectMetadata
    rooms: List[RoomData] = field(default_factory=list)
    luminaires: List[LuminaireReference] = field(default_factory=list)
    calculation_settings: CalculationSettings = field(default_factory=CalculationSettings)
    
    # Results (not always saved)
    results_available: bool = False
    last_calculation_time: Optional[str] = None
    
    # Custom materials
    custom_materials: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Notes and annotations
    notes: str = ""
    
    def add_room(self, room: Room, room_id: str = None) -> str:
        """Add a room to the project."""
        room_data = RoomData.from_room(room, room_id)
        self.rooms.append(room_data)
        return room_data.id
    
    def add_luminaire(
        self,
        name: str,
        position: Tuple[float, float, float],
        ies_filename: str = None,
        ies_content: str = None,
        **kwargs
    ) -> str:
        """Add a luminaire to the project."""
        lum = LuminaireReference(
            id=str(uuid.uuid4()),
            name=name,
            ies_filename=ies_filename,
            ies_data_embedded=base64.b64encode(ies_content.encode()).decode() if ies_content else None,
            position=position,
            **kwargs
        )
        self.luminaires.append(lum)
        return lum.id
    
    def get_room(self, room_id: str) -> Optional[RoomData]:
        """Get room by ID."""
        for room in self.rooms:
            if room.id == room_id:
                return room
        return None
    
    def get_luminaire(self, lum_id: str) -> Optional[LuminaireReference]:
        """Get luminaire by ID."""
        for lum in self.luminaires:
            if lum.id == lum_id:
                return lum
        return None
    
    def to_scene(self) -> Scene:
        """Convert to Scene object for calculations."""
        scene = Scene(name=self.metadata.name)
        for room_data in self.rooms:
            scene.add_room(room_data.to_room())
        return scene


# =============================================================================
# File I/O
# =============================================================================

def _serialize_project(project: LuxeraProject) -> Dict[str, Any]:
    """Convert project to serializable dict."""
    return {
        'version': '1.0',
        'metadata': asdict(project.metadata),
        'rooms': [asdict(r) for r in project.rooms],
        'luminaires': [asdict(l) for l in project.luminaires],
        'calculation_settings': asdict(project.calculation_settings),
        'results_available': project.results_available,
        'last_calculation_time': project.last_calculation_time,
        'custom_materials': project.custom_materials,
        'notes': project.notes,
    }


def _deserialize_project(data: Dict[str, Any]) -> LuxeraProject:
    """Create project from dict."""
    metadata = ProjectMetadata(**data.get('metadata', {'name': 'Untitled'}))
    
    rooms = [RoomData(**r) for r in data.get('rooms', [])]
    luminaires = [LuminaireReference(**l) for l in data.get('luminaires', [])]
    
    calc_settings = CalculationSettings(**data.get('calculation_settings', {}))
    
    return LuxeraProject(
        metadata=metadata,
        rooms=rooms,
        luminaires=luminaires,
        calculation_settings=calc_settings,
        results_available=data.get('results_available', False),
        last_calculation_time=data.get('last_calculation_time'),
        custom_materials=data.get('custom_materials', {}),
        notes=data.get('notes', ''),
    )


def save_project(project: LuxeraProject, filepath: Path, compress: bool = True) -> None:
    """
    Save project to file.
    
    Args:
        project: Project to save
        filepath: Output file path (.luxera)
        compress: Whether to gzip compress the file
    """
    filepath = Path(filepath)
    if not filepath.suffix:
        filepath = filepath.with_suffix('.luxera')
    
    project.metadata.update_modified()
    
    data = _serialize_project(project)
    json_str = json.dumps(data, indent=2)
    
    if compress:
        with gzip.open(filepath, 'wt', encoding='utf-8') as f:
            f.write(json_str)
    else:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(json_str)


def load_project(filepath: Path) -> LuxeraProject:
    """
    Load project from file.
    
    Args:
        filepath: Input file path (.luxera)
    
    Returns:
        Loaded LuxeraProject
    """
    filepath = Path(filepath)
    
    try:
        # Try compressed first
        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            json_str = f.read()
    except gzip.BadGzipFile:
        # Fall back to uncompressed
        with open(filepath, 'r', encoding='utf-8') as f:
            json_str = f.read()
    
    data = json.loads(json_str)
    return _deserialize_project(data)


def create_new_project(name: str, author: str = "", company: str = "") -> LuxeraProject:
    """
    Create a new empty project.
    
    Args:
        name: Project name
        author: Author name
        company: Company name
    
    Returns:
        New LuxeraProject
    """
    now = datetime.now().isoformat()
    
    metadata = ProjectMetadata(
        name=name,
        author=author,
        company=company,
        created_at=now,
        modified_at=now,
    )
    
    return LuxeraProject(metadata=metadata)


# =============================================================================
# Project Templates
# =============================================================================

def create_office_project(
    name: str,
    room_width: float = 6.0,
    room_length: float = 8.0,
    room_height: float = 2.8,
) -> LuxeraProject:
    """Create a typical office project template."""
    project = create_new_project(name)
    
    # Add room
    room = Room.rectangular(
        name="Office",
        width=room_width,
        length=room_length,
        height=room_height,
        floor_material=MATERIALS['carpet_medium'],
        ceiling_material=MATERIALS['acoustic_ceiling'],
        wall_material=MATERIALS['light_gray'],
    )
    project.add_room(room)
    
    # Set calculation settings for office
    project.calculation_settings.work_plane_height = 0.8
    project.calculation_settings.target_activity_type = ActivityType.OFFICE_GENERAL.name
    
    return project


def create_warehouse_project(
    name: str,
    width: float = 20.0,
    length: float = 30.0,
    height: float = 6.0,
) -> LuxeraProject:
    """Create a warehouse project template."""
    project = create_new_project(name)
    
    room = Room.rectangular(
        name="Warehouse",
        width=width,
        length=length,
        height=height,
        floor_material=MATERIALS['concrete'],
        ceiling_material=MATERIALS['light_gray'],
        wall_material=MATERIALS['medium_gray'],
    )
    project.add_room(room)
    
    project.calculation_settings.work_plane_height = 0.0  # Floor level
    project.calculation_settings.target_activity_type = ActivityType.WAREHOUSE_GENERAL.name
    
    return project
