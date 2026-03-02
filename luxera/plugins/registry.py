from __future__ import annotations

import importlib
import importlib.metadata
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from luxera.plugins.interfaces import (
    CalculationBackendPlugin,
    ComplianceRulePlugin,
    ImportFormatPlugin,
    MaterialLibraryPlugin,
    PhotometrySourcePlugin,
    ReportTemplatePlugin,
)
from luxera.plugins.manifest import PluginManifest


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    instance: Any


class PluginRegistry:
    """
    Discovers, loads, and manages Luxera plugins.

    Plugins are Python packages installed in the environment with
    a luxera_plugin.json manifest file, OR directories in
    ~/.luxera/plugins/ with the same manifest.
    """

    def __init__(self, plugin_dirs: Optional[List[Path]] = None):
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._dirs = [Path(p).expanduser().resolve() for p in (plugin_dirs or [Path.home() / ".luxera" / "plugins"])]

    def discover(self) -> List[PluginManifest]:
        """
        Scan plugin directories for luxera_plugin.json manifests.
        Also scan installed Python packages for entry_points group "luxera.plugins".
        Return list of discovered manifests.
        """
        manifests: List[PluginManifest] = []
        seen: set[tuple[str, str]] = set()

        for base in self._dirs:
            if not base.exists() or not base.is_dir():
                continue
            for mf in base.rglob("luxera_plugin.json"):
                try:
                    manifest = PluginManifest.from_json_file(mf)
                except Exception:
                    continue
                key = (manifest.name, manifest.version)
                if key in seen:
                    continue
                seen.add(key)
                manifests.append(manifest)

        # Entry points discovery fallback for installed plugins.
        try:
            eps = importlib.metadata.entry_points()
            group_eps = eps.select(group="luxera.plugins") if hasattr(eps, "select") else eps.get("luxera.plugins", [])
        except Exception:
            group_eps = []

        for ep in group_eps:
            try:
                manifest = PluginManifest(
                    name=str(ep.name),
                    version="0.0.0",
                    author="unknown",
                    description=f"Installed entry point plugin: {ep.value}",
                    plugin_type="material_library",
                    entry_point=str(ep.value).replace(":", "."),
                )
            except Exception:
                continue
            key = (manifest.name, manifest.version)
            if key in seen:
                continue
            seen.add(key)
            manifests.append(manifest)

        return manifests

    def load(self, manifest: PluginManifest) -> LoadedPlugin:
        """
        Import the entry_point module and instantiate the plugin class.
        Validate it implements the correct interface for its plugin_type.
        """
        module_name, class_name = self._split_entry_point(manifest.entry_point)
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        instance = cls()
        self._validate_plugin_type(manifest.plugin_type, instance)

        loaded = LoadedPlugin(manifest=manifest, instance=instance)
        self._plugins[manifest.name] = loaded
        return loaded

    def load_all(self):
        """Discover and load all available plugins."""
        for manifest in self.discover():
            try:
                self.load(manifest)
            except Exception:
                continue

    def get_plugins_by_type(self, plugin_type: str) -> List[LoadedPlugin]:
        """Return all loaded plugins of a given type."""
        ptype = str(plugin_type)
        return [p for p in self._plugins.values() if p.manifest.plugin_type == ptype]

    @staticmethod
    def _split_entry_point(entry_point: str) -> tuple[str, str]:
        raw = str(entry_point).strip()
        if ":" in raw:
            mod, cls = raw.split(":", 1)
            if not mod or not cls:
                raise ValueError(f"Invalid entry point: {entry_point}")
            return mod, cls
        if "." not in raw:
            raise ValueError(f"Invalid dotted entry point: {entry_point}")
        mod, cls = raw.rsplit(".", 1)
        return mod, cls

    @staticmethod
    def _validate_plugin_type(plugin_type: str, instance: Any) -> None:
        iface_map = {
            "photometry_source": PhotometrySourcePlugin,
            "compliance_rule": ComplianceRulePlugin,
            "report_template": ReportTemplatePlugin,
            "material_library": MaterialLibraryPlugin,
            "calculation_backend": CalculationBackendPlugin,
            "import_format": ImportFormatPlugin,
        }
        iface = iface_map.get(str(plugin_type))
        if iface is None:
            raise ValueError(f"Unsupported plugin_type: {plugin_type}")
        if not isinstance(instance, iface):
            raise TypeError(f"Plugin instance does not implement required interface for {plugin_type}")
