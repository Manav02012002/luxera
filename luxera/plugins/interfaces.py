from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List


class PhotometrySourcePlugin(ABC):
    """Plugin that provides photometric files."""

    @abstractmethod
    def search(self, query: str, **filters) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def download(self, record_id: str) -> bytes:
        ...


class ComplianceRulePlugin(ABC):
    """Plugin that adds custom compliance checking rules."""

    @abstractmethod
    def check(self, project: Any, results: Any) -> List[Dict[str, Any]]:
        ...


class ReportTemplatePlugin(ABC):
    """Plugin that provides custom PDF report templates."""

    @abstractmethod
    def generate(self, project: Any, results: Any, output_path: Path):
        ...


class MaterialLibraryPlugin(ABC):
    """Plugin that provides material definitions."""

    @abstractmethod
    def get_materials(self) -> Dict[str, Any]:
        ...


class CalculationBackendPlugin(ABC):
    """Plugin that provides a custom calculation backend."""

    @abstractmethod
    def run(self, project: Any, job: Any) -> Dict[str, Any]:
        ...


class ImportFormatPlugin(ABC):
    """Plugin that imports custom geometry/scene formats."""

    @abstractmethod
    def import_file(self, path: Path, **options) -> Dict[str, Any]:
        ...
