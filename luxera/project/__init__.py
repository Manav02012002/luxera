"""
Luxera Project Module

Project file handling for saving and loading Luxera projects.
"""

from luxera.project.project_file import (
    LuminaireReference,
    RoomData,
    CalculationSettings,
    ProjectMetadata,
    LuxeraProject,
    save_project,
    load_project,
    create_new_project,
    create_office_project,
    create_warehouse_project,
)
from luxera.project.schema import (
    Project,
    Geometry,
    RoomSpec,
    MaterialSpec,
    MaterialLibraryEntry,
    PhotometryAsset,
    LuminaireFamily,
    LuminaireInstance,
    CalcGrid,
    JobSpec,
    JobResultRef,
)
from luxera.project.io import save_project_schema, load_project_schema
from luxera.project.presets import en12464_direct_job, en13032_radiosity_job

__all__ = [
    "LuminaireReference",
    "RoomData",
    "CalculationSettings",
    "ProjectMetadata",
    "LuxeraProject",
    "save_project",
    "load_project",
    "create_new_project",
    "create_office_project",
    "create_warehouse_project",
    "Project",
    "Geometry",
    "RoomSpec",
    "MaterialSpec",
    "MaterialLibraryEntry",
    "PhotometryAsset",
    "LuminaireFamily",
    "LuminaireInstance",
    "CalcGrid",
    "JobSpec",
    "JobResultRef",
    "save_project_schema",
    "load_project_schema",
    "en12464_direct_job",
    "en13032_radiosity_job",
]
