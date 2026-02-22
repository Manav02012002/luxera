"""
Luxera Luminaire Database Module

Manages luminaire catalogs and photometric data.
"""

from luxera.database.catalog import (
    LuminaireRecord,
    LuminaireCatalog,
    create_catalog,
    load_catalog,
    save_catalog,
    import_ies_to_catalog,
)
from luxera.database.library_manager import (
    IndexStats,
    LibraryEntry,
    index_folder,
    list_all_entries,
    search_db,
)

__all__ = [
    "LuminaireRecord",
    "LuminaireCatalog",
    "create_catalog",
    "load_catalog",
    "save_catalog",
    "import_ies_to_catalog",
    "LibraryEntry",
    "IndexStats",
    "index_folder",
    "search_db",
    "list_all_entries",
]
