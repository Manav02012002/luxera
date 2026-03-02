from __future__ import annotations

import json
from pathlib import Path

from luxera.plugins.interfaces import MaterialLibraryPlugin
from luxera.plugins.manifest import PluginManifest
from luxera.plugins.registry import PluginRegistry


def test_manifest_parsing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "luxera_plugin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "name": "demo-plugin",
                "version": "1.2.0",
                "author": "QA",
                "description": "demo",
                "plugin_type": "material_library",
                "entry_point": "luxera.plugins.example_plugin.ExtraMaterialsPlugin",
            }
        ),
        encoding="utf-8",
    )
    m = PluginManifest.from_json_file(manifest_path)
    assert m.name == "demo-plugin"
    assert m.version == "1.2.0"
    assert m.plugin_type == "material_library"


def test_discover_local_plugin(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "demo"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "luxera_plugin.json").write_text(
        json.dumps(
            {
                "name": "local-demo",
                "version": "0.1.0",
                "author": "Local",
                "description": "local plugin",
                "plugin_type": "material_library",
                "entry_point": "luxera.plugins.example_plugin.ExtraMaterialsPlugin",
            }
        ),
        encoding="utf-8",
    )

    registry = PluginRegistry(plugin_dirs=[tmp_path / "plugins"])
    manifests = registry.discover()
    assert any(m.name == "local-demo" for m in manifests)


def test_load_example_plugin() -> None:
    manifest_path = Path("luxera/plugins/luxera_plugin.json").resolve()
    manifest = PluginManifest.from_json_file(manifest_path)
    registry = PluginRegistry(plugin_dirs=[])
    loaded = registry.load(manifest)
    assert isinstance(loaded.instance, MaterialLibraryPlugin)
    mats = loaded.instance.get_materials()
    assert len(mats) >= 5


def test_get_plugins_by_type() -> None:
    manifest_path = Path("luxera/plugins/luxera_plugin.json").resolve()
    manifest = PluginManifest.from_json_file(manifest_path)
    registry = PluginRegistry(plugin_dirs=[])
    registry.load(manifest)
    mats = registry.get_plugins_by_type("material_library")
    assert mats
    assert mats[0].manifest.plugin_type == "material_library"


def test_invalid_manifest_skipped(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "broken"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "luxera_plugin.json").write_text(
        json.dumps(
            {
                "name": "broken-plugin",
                "version": "0.1.0",
                # missing author/description/plugin_type/entry_point
            }
        ),
        encoding="utf-8",
    )

    registry = PluginRegistry(plugin_dirs=[tmp_path / "plugins"])
    manifests = registry.discover()
    assert all(m.name != "broken-plugin" for m in manifests)
