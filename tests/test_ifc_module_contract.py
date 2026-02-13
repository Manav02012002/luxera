from __future__ import annotations

import importlib


def test_ifc_import_module_exists_for_contract() -> None:
    mod = importlib.import_module("luxera.ifc.import")
    assert hasattr(mod, "import_ifc_deterministic")

