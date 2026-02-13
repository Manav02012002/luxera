from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from luxera.project.schema import Project


def _now_ifc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def export_ifc_spaces_and_luminaires(project: Project, out_path: str | Path) -> Path:
    """Write a minimal IFC STEP file containing IfcSpace and IfcLightFixture entities."""
    out = Path(out_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("ISO-10303-21;")
    lines.append("HEADER;")
    lines.append("FILE_DESCRIPTION(('ViewDefinition [CoordinationView_V2.0]'),'2;1');")
    lines.append(f"FILE_NAME('{out.name}','{_now_ifc()}',('Luxera'),('Luxera'),'Luxera','Luxera','');")
    lines.append("FILE_SCHEMA(('IFC4'));")
    lines.append("ENDSEC;")
    lines.append("DATA;")

    eid = 1

    def add(row: str) -> int:
        nonlocal eid
        i = eid
        lines.append(f"#{i}={row};")
        eid += 1
        return i

    org = add("IFCORGANIZATION($,'Luxera',$,$,$)")
    app = add(f"IFCAPPLICATION(#{org},'0.1','Luxera','LUXERA')")
    person = add("IFCPERSON($,$,'User',$,$,$,$,$)")
    pao = add(f"IFCPERSONANDORGANIZATION(#{person},#{org},$)")
    owner = add(f"IFCOWNERHISTORY(#{pao},#{app},$,.ADDED.,$,$,$,0)")
    proj = add(f"IFCPROJECT('0',$,'{project.name or 'Project'}',$,$,$,$,$,$)")

    for room in project.geometry.rooms:
        rid = str(room.id).replace("'", "")
        name = str(room.name or room.id).replace("'", "")
        add(f"IFCSPACE('{rid}',#{owner},'{name}',$,$,$,$,$,.INTERNAL.,$)")

    for lum in project.luminaires:
        lid = str(lum.id).replace("'", "")
        name = str(lum.name or lum.id).replace("'", "")
        add(f"IFCLIGHTFIXTURE('{lid}',#{owner},'{name}',$,$,$,$,$)")

    _ = proj
    lines.append("ENDSEC;")
    lines.append("END-ISO-10303-21;")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
