from __future__ import annotations

from typing import Any, Dict

from luxera.plugins.interfaces import MaterialLibraryPlugin


class ExtraMaterialsPlugin(MaterialLibraryPlugin):
    """Example plugin that provides additional materials."""

    def get_materials(self) -> Dict[str, Any]:
        return {
            "CONCRETE_POLISHED": {"reflectance": 0.35, "specularity": 0.10},
            "TIMBER_LIGHT": {"reflectance": 0.45, "specularity": 0.08},
            "TIMBER_DARK": {"reflectance": 0.20, "specularity": 0.06},
            "FABRIC_BLACKOUT": {"reflectance": 0.05, "specularity": 0.02},
            "ALUMINUM_BRUSHED": {"reflectance": 0.60, "specularity": 0.35},
        }
