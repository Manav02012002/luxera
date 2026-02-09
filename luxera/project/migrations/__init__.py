"""Project schema migrations."""

from luxera.project.migrations.v1_to_v2 import migrate as migrate_v1_to_v2
from luxera.project.migrations.v2_to_v3 import migrate as migrate_v2_to_v3
from luxera.project.migrations.v3_to_v4 import migrate as migrate_v3_to_v4
from luxera.project.migrations.v4_to_v5 import migrate as migrate_v4_to_v5


def migrate_project(data):
    version = data.get("schema_version", 1)
    if version == 1:
        data = migrate_v1_to_v2(data)
        version = data.get("schema_version", 2)
    if version == 2:
        data = migrate_v2_to_v3(data)
        version = data.get("schema_version", 3)
    if version == 3:
        data = migrate_v3_to_v4(data)
        version = data.get("schema_version", 4)
    if version == 4:
        data = migrate_v4_to_v5(data)
    return data
